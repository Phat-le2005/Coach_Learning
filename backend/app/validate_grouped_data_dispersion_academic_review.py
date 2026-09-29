from __future__ import annotations
import argparse
import json
from app.questions.grouped_data_dispersion_academic_review import GroupedDataDispersionAcademicReviewValidator

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate DATA-MATH12-021 grouped-data dispersion academic review.")
    parser.parse_args(argv)
    report = GroupedDataDispersionAcademicReviewValidator().validate()
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return 0 if report.is_valid else 1

if __name__ == "__main__":
    raise SystemExit(main())
