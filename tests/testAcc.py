"""手動驗收腳本：config、Evidence 與 baseline storage 基本流程。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

import config
import evidence
import storage


def main():
    print(config.SUPPORTED_SYMBOLS)
    print(config.BASELINE_END_DATE)

    evidence.reset_stores()
    evidence_id = evidence.log_evidence(
        "run_001",
        "test_tool",
        "測試用途說明",
        {
            "schema_version": "1.0",
            "status": "success",
            "raw": {},
            "source": "test",
            "content_reference": {},
            "summary": "test",
        },
    )
    print(evidence.evidence_list)
    print(evidence_id)

    result = evidence.log_evidence(
        "run_001", "test_tool", "", {"source": "test"}
    )
    print(result)
    print(len(evidence.evidence_list))

    dataframe = storage.read_baseline_csv("SOL")
    print(dataframe.head())


if __name__ == "__main__":
    main()
