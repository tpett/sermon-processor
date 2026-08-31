@interface @needs-decision
Feature: Access control
  In order to keep an unfinished sermon cut off the public internet
  As the owner of the system
  I want to control who can see and act on recordings

  The recorder's web interface has no authentication and relies on network-level
  protection. This system is different: it triggers notifications to people and
  produces publishable artifacts, so it may need to be reachable from a phone.

  # Q38 — is this on a private network like the recorder, or exposed publicly?
  # Q39 — how many people review? Is one shared login acceptable?

  Rule: Unauthenticated visitors see nothing

    @happy-path
    Scenario Outline: Protected pages require signing in
      Given I am not signed in
      When I visit "<page>"
      Then I am redirected to the sign-in page
      And I see no recording data

      Examples:
        | page                    |
        | the recordings list     |
        | a recording detail view |
        | an artifact download    |
        | the system health view  |

    @happy-path
    Scenario: Signing in
      Given a reviewer account exists
      When I sign in with valid credentials
      Then I am taken to the recordings list

    @edge-case
    Scenario: Signing in with bad credentials
      When I sign in with invalid credentials
      Then I am told the credentials are not valid
      And repeated failures are rate limited

  Rule: Roles separate reviewing from administering

    @assumption
    Scenario Outline: What each role can do
      # Q40 — is a role distinction worth it for a church of this size?
      Given I am signed in as "<role>"
      Then I can "<allowed>"
      And I cannot "<denied>"

      Examples:
        | role      | allowed                            | denied                          |
        | reviewer  | adjust boundaries and approve      | change system configuration     |
        | admin     | change system configuration        |                                 |

  Rule: Actions are attributable

    @happy-path
    Scenario: Every human action records who did it
      Given I am signed in as "reviewer@example.com"
      When I approve a Recording
      Then the approval records "reviewer@example.com"
      And the processing log shows my name against the action

  Rule: Artifact links are not guessable

    @edge-case
    Scenario: Sharing a download link
      Given a Recording is "complete"
      When I copy the MP3 download link and open it while signed out
      Then I am asked to sign in
      # Q41 — or do you want time-limited signed links so you can hand the MP3
      # to someone who has no account?
