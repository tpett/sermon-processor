Feature: Step definitions are discovered wherever the harness keeps them
  In order to tell a wrong step pattern apart from an unread directory
  As someone writing step definitions
  I want a definition placed anywhere under tests/steps to be found

  Scenario: A definition kept in tests/steps is found
    Given a step definition that lives in tests/steps
    Then the harness reports it was found in tests/steps

  Scenario: A definition kept in a subdirectory of tests/steps is found
    Given a step definition that lives in a subdirectory of tests/steps
    Then the harness reports it was found in tests/steps/nested
