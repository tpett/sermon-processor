Feature: Step definitions are discovered wherever the harness keeps them
  In order to tell a wrong step pattern apart from an unread directory
  As someone writing step definitions
  I want a definition placed in tests/steps to be found

  Scenario: A definition kept in tests/steps is found
    Given a step definition that lives in tests/steps
    Then the harness has discovered it
