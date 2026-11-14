"""Fine-tune a multi-label transformer on the 5 mental-health axes.

Data sources (merged):
  1. GoEmotions (HF, English) -> anxiety (fear, nervousness) and mood (sadness, grief, disappointment, remorse).
                               The other 3 axes are UNKNOWN for these rows -> masked out of the loss.
  2. data/synthetic.jsonl   -> all 5 axes known, in FRENCH (made by scripts/generate_data.py).
     A multilingual encoder (XLM-R) transfers the English emotion signal to French.
  3. --extra file.jsonl     -> optional, e.g. Dreaddit mapped to anxiety, or real annotated data.

Key idea: MASKED BCE. A label = -1 means "unknown, don't penalise". This stops the model from
learning "GoEmotions text is never about sleep" which would be a dataset artifact, not a fact.

Run (Colab/Kaggle GPU recommended, ~10-20 min):
  uv run python scripts/train.py --out models/xlmr-fr
Then:  HACKPSY_MODEL_DIR=models/xlmr-fr uv run hackpsyassistant
"""
import argparse, json, os, random
import numpy as np
import torch
from datasets import Dataset, load_dataset
from sklearn.metrics import f1_score, recall_score
from sklearn.model_selection import train_test_split
from transformers import (AutoModelForSequenceClassification, AutoTokenizer, Trainer,
                          TrainingArguments, DataCollatorWithPadding)

AXES = ["anxiety", "mood", "sleep", "isolation", "selfharm"]
RISK = {"selfharm"}
GOEMO_MAP = {"anxiety": ["fear", "nervousness"],
             "mood": ["sadness", "grief", "disappointment", "remorse"]}


def load_goemotions(limit):
    ds = load_dataset("google-research-datasets/go_emotions", "simplified")
    names = ds["train"].features["labels"].feature.names
    idx = {a: [names.index(n) for n in ns] for a, ns in GOEMO_MAP.items()}
    rows = []
    for split in ("train", "validation", "test"):
        for ex in ds[split]:
            lab = {a: -1 for a in AXES}            # unknown by default
            for a, ids in idx.items():
                lab[a] = int(any(i in ex["labels"] for i in ids))
            rows.append({"text": ex["text"], "labels": [lab[a] for a in AXES]})
    random.shuffle(rows)
    # keep positives plus a sample of negatives to limit imbalance / training time
    pos = [r for r in rows if 1 in r["labels"]]
    neg = [r for r in rows if 1 not in r["labels"]][: max(limit - len(pos), 0)]
    return pos + neg


def load_jsonl(path):
    out = []
    for line in open(path):
        d = json.loads(line)
        out.append({"text": d["text"], "labels": [d["labels"].get(a, -1) for a in AXES]})
    return out


class MaskedTrainer(Trainer):
    def __init__(self, *a, pos_weight=None, **k):
        super().__init__(*a, **k)
        self.pos_weight = pos_weight

    def compute_loss(self, model, inputs, return_outputs=False, **kw):
        labels = inputs.pop("labels").float()
        out = model(**inputs)
        mask = (labels >= 0).float()
        loss = torch.nn.functional.binary_cross_entropy_with_logits(
            out.logits, labels.clamp(min=0), reduction="none",
            pos_weight=self.pos_weight.to(out.logits.device))
        loss = (loss * mask).sum() / mask.sum().clamp(min=1)
        return (loss, out) if return_outputs else loss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="FacebookAI/xlm-roberta-base",
                    help="multilingual, ungated. Alternatives: almanach/camembert-base (French only), "
                         "distilbert-base-multilingual-cased (faster). English-only: mental/mental-bert-base-uncased (gated)")
    ap.add_argument("--out", default="models/xlmr-fr")
    ap.add_argument("--synthetic", default="data/synthetic.jsonl")
    ap.add_argument("--extra", default=None)
    ap.add_argument("--goemo-limit", type=int, default=20000)
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--bs", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=128)
    a = ap.parse_args()
    random.seed(0); np.random.seed(0); torch.manual_seed(0)

    rows = load_goemotions(a.goemo_limit)
    if os.path.exists(a.synthetic):
        rows += load_jsonl(a.synthetic)
    else:
        print(f"!! {a.synthetic} missing: sleep/isolation/selfharm will have NO training signal")
    if a.extra:
        rows += load_jsonl(a.extra)
    print("total rows:", len(rows))

    train, test = train_test_split(rows, test_size=0.15, random_state=0)
    train, val = train_test_split(train, test_size=0.1, random_state=0)

    tok = AutoTokenizer.from_pretrained(a.model)
    enc = lambda b: tok(b["text"], truncation=True, max_length=a.max_len)
    mk = lambda r: Dataset.from_list(r).map(enc, batched=True, remove_columns=["text"])
    dtrain, dval, dtest = mk(train), mk(val), mk(test)

    # pos_weight per axis from known labels (handles class imbalance)
    L = np.array([r["labels"] for r in train])
    pw = []
    for j in range(len(AXES)):
        col = L[:, j]; p, n = (col == 1).sum(), (col == 0).sum()
        pw.append(float(np.clip(n / max(p, 1), 1, 10)))
    print("pos_weight:", dict(zip(AXES, pw)))

    model = AutoModelForSequenceClassification.from_pretrained(
        a.model, num_labels=len(AXES), problem_type="multi_label_classification",
        id2label=dict(enumerate(AXES)), label2id={k: i for i, k in enumerate(AXES)})

    def metrics(p):
        probs = 1 / (1 + np.exp(-p.predictions)); y = p.label_ids
        res = {}
        for j, ax in enumerate(AXES):
            m = y[:, j] >= 0
            if m.sum() == 0 or len(set(y[m, j])) < 2: continue
            pred = (probs[m, j] > 0.5).astype(int)
            res[f"f1_{ax}"] = f1_score(y[m, j], pred, zero_division=0)
            res[f"recall_{ax}"] = recall_score(y[m, j], pred, zero_division=0)
        f1s = [v for k, v in res.items() if k.startswith("f1_")]
        res["macro_f1"] = float(np.mean(f1s)) if f1s else 0.0
        return res

    steps_per_epoch = max(1, (len(dtrain) + a.bs - 1) // a.bs)
    args = TrainingArguments(
        output_dir=a.out, num_train_epochs=a.epochs, learning_rate=a.lr,
        per_device_train_batch_size=a.bs, per_device_eval_batch_size=64,
        weight_decay=0.01, warmup_steps=int(0.1 * steps_per_epoch * a.epochs),
        eval_strategy="epoch", save_strategy="epoch",
        load_best_model_at_end=True, metric_for_best_model="macro_f1",
        save_total_limit=1, logging_steps=50, report_to="none", fp16=torch.cuda.is_available())
    tr = MaskedTrainer(model=model, args=args, train_dataset=dtrain, eval_dataset=dval,
                       data_collator=DataCollatorWithPadding(tok), compute_metrics=metrics,
                       pos_weight=torch.tensor(pw))
    tr.train()
    print("TEST:", json.dumps(tr.evaluate(dtest, metric_key_prefix="test"), indent=2))
    tr.save_model(a.out); tok.save_pretrained(a.out)
    print("saved to", a.out)


if __name__ == "__main__":
    main()
