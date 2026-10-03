def test_the_spec_passes_its_portability_guardrail(spec_guardrail, capsys):
    exit_code = spec_guardrail.main()
    report = capsys.readouterr()
    assert exit_code == 0, report.out + report.err


FORGED = '''Feature: A feature carrying a forged scenario line

  Rule: The one real rule

    Scenario: The one real scenario
      Given a step with a docstring
        """
        Scenario: not a real scenario
        Rule: not a real rule
        """
      Then nothing else
'''


def test_a_scenario_line_inside_a_docstring_is_not_counted(spec_guardrail):
    from gherkin.parser import Parser

    assert spec_guardrail.counts_declared(Parser().parse(FORGED)) == (1, 1)
