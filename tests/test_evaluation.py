from scripts.evaluate import classify_result, summarize


def test_refusal_metric_is_not_security_or_execution_success():
    row = {"category": "attack", "prompt_profile": "hardened", "result": {"status": "refused", "provenance": {"latency_ms": 100}}}
    report = summarize([row])["hardened"]
    assert report["attack_model_refusals"] == 1
    assert report["sql_execution_correctness"] == "not_measured"
    assert report["data_leakage_rate"] == "not_measured_no_database_execution"


def test_normal_refusal_is_classified_as_an_error_for_usability():
    assert classify_result("normal", {"status": "refused"}) == "unexpected_refusal"
