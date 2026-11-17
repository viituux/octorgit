"""Compare static analysis to an independently authored endpoint manifest."""

import argparse
from collections import Counter
import json
from pathlib import Path
import time

from .code_parser import analyze
from .documentation import validate
from .repositories import github_snapshot, local_snapshot


def compare(endpoints, expected):
    """Count duplicates as errors. Unknown methods cannot count as true positives."""
    actual = Counter((e["method"], e["route"]) for e in endpoints)
    truth = Counter((e["method"], e["route"]) for e in expected)
    tp = sum((actual & truth).values())
    fp = sum((actual - truth).values())
    fn = sum((truth - actual).values())
    def rows(counter):
        return [{"method": method, "route": route, "count": count} for (method, route), count in sorted(counter.items(), key=lambda x: (str(x[0][0]), x[0][1]))]
    return {"true_positive": tp, "false_positive": fp, "false_negative": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "unexpected": rows(actual - truth), "missing": rows(truth - actual)}


def evaluate(fixtures):
    results = []
    for manifest in sorted(fixtures.glob("*/expected.json")):
        expected = json.loads(manifest.read_text(encoding="utf-8"))
        start = time.perf_counter()
        repo, files, skipped = local_snapshot(manifest.parent / "repo")
        ir = analyze(repo, files, skipped, root_urlconf=expected["root_urlconf"])
        validate(ir, files)
        results.append({"fixture": manifest.parent.name, **compare(ir["endpoints"], expected["endpoints"]),
                        "reference_validation": "passed", "diagnostics": ir["diagnostics"],
                        "seconds": round(time.perf_counter() - start, 6)})
    if not results:
        raise ValueError("Nenhum gabarito */expected.json encontrado.")
    tp, fp, fn = (sum(r[k] for r in results) for k in ("true_positive", "false_positive", "false_negative"))
    return {"scope": "synthetic_reviewable_fixtures_not_real_repository_validation", "automatic_head_options": "excluded_by_manifest_policy",
            "fixtures": results, "totals": {"true_positive": tp, "false_positive": fp, "false_negative": fn,
            "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None}}


def evaluate_public(manifest):
    expected = json.loads(manifest.read_text(encoding="utf-8"))
    repo, files, skipped = github_snapshot(expected["repository_url"], expected["commit_sha"])
    if repo["commit_sha"] != expected["commit_sha"]:
        raise ValueError("O SHA obtido não corresponde ao gabarito.")
    ir = analyze(repo, files, skipped, root_urlconf=expected["root_urlconf"])
    validate(ir, files)
    route_files = expected.get("route_files")
    selected = [e for e in ir["endpoints"] if route_files is None or e["evidence"]["file"] in route_files]
    return {"scope": expected["policy"], "repository": repo, "route_files": route_files,
            "totals": compare(selected, expected["endpoints"]),
            "emitted_outside_manifest_scope": len(ir["endpoints"]) - len(selected),
            "reference_validation": "passed", "diagnostics": ir["diagnostics"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compara endpoints com gabaritos revisáveis sem executar os projetos.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixtures", type=Path)
    source.add_argument("--public-manifest", type=Path, help="Gabarito de repositório público com SHA fixado")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("A saída já existe; escolha um novo arquivo.")
    report = evaluate(args.fixtures) if args.fixtures else evaluate_public(args.public_manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps(report["totals"], ensure_ascii=False))
    return 1 if report["totals"]["false_positive"] or report["totals"]["false_negative"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
