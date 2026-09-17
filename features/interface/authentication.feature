@interface
Feature: Access control
  In order to keep an unfinished sermon cut off the public internet
  As the owner of the system
  I want the tailnet to be the perimeter, and nothing else in the way

  Settled 2026-09-16: **no authentication.** "We can start with NoAuth. We don't
  have Auth on the recorder right now."

  The recorder already works this way, and so does the Garage S3 instance the
  recordings live in. Everything is on one tailnet, one person reviews, and a
  sign-in screen between him and the approve button buys nothing that the tailnet
  does not already provide. Q38, Q39, Q40 and Q41 are answered by this and need
  no separate decision.

  What this costs, stated plainly so it is a choice and not an oversight: any
  device on the tailnet can approve and publish, actions cannot be attributed to
  a person, and an artifact link works for anyone who can reach the host. All
  three are acceptable at one reviewer and stop being acceptable at two.

  Rule: The network is the boundary

    @happy-path
    Scenario Outline: Every page is reachable without signing in
      Given I am on the tailnet
      When I visit "<page>"
      Then I see the page
      And I am not asked to sign in

      Examples:
        | page                    |
        | the recordings list     |
        | a recording detail view |
        | an artifact download    |
        | the system health view  |

    @happy-path
    Scenario: The service does not listen on the public internet
      Then the service binds only to its tailnet interface
      And it is not reachable from outside the tailnet
      # This is the whole of the access control. If it is ever bound to a public
      # interface, everything above becomes wrong at once.

  Rule: Actions are attributed to the system, not to a person

    @happy-path
    Scenario: An approval records what happened, not who did it
      When a Recording is approved
      Then the approval is recorded with its timestamp
      And the actor is recorded as "reviewer"
      # There is one reviewer. When there is more than one, this is the scenario
      # that has to change first, and `approval.feature` reads the actor from
      # here rather than assuming a name.

  Rule: Adding authentication later must not require reshaping anything

    @assumption
    Scenario: The reviewer identity is a seam, not a constant
      Given the system records an actor on every human action
      Then adding real accounts changes who that actor is
      And it does not change what is recorded against it
