from app.questions.grouped_data_dispersion_academic_review import GroupedDataDispersionAcademicReviewValidator
from app.validate_grouped_data_dispersion_academic_review import main

def test_data_math12_021_review_contract_passes():
    report = GroupedDataDispersionAcademicReviewValidator().validate()
    assert report.is_valid, report.as_dict()
    assert report.counts["standalone_reviews"] == 39
    assert report.counts["group_reviews"] == 2
    assert report.counts["verified"] == 38
    assert report.counts["hold"] == 3
    assert report.counts["production_release_eligible"] == 0

def test_data_math12_021_cli(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert '"status": "PASS"' in out
