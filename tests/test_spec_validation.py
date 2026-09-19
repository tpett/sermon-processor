def test_the_spec_passes_its_portability_guardrail(spec_guardrail, capsys):
    exit_code = spec_guardrail.main()
    report = capsys.readouterr()
    assert exit_code == 0, report.out + report.err
