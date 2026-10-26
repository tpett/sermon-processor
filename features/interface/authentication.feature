@interface
Feature: Access control
  In order to keep an unfinished sermon cut off the public internet
  As the owner of the system
  I want the tailnet to be one perimeter and a sign-in to be the other

  Settled 2026-09-16: **no authentication.** "We can start with NoAuth. We don't
  have Auth on the recorder right now."

  Settled 2026-10-26, changing that: the service is also reached from the public
  internet, through Cloudflare Access, which asks a person to sign in and passes
  the request on with a signed statement of who they are. The service checks that
  statement itself rather than trusting where the request came from. The
  recordings are too large to be carried through Cloudflare, so the tailnet host
  stays open: a request for it that did not come through Cloudflare needs no
  sign-in, and neither does the Recorder's webhook, which reaches the service
  there and answers to its bearer token alone.

  Sign-in is a deployment setting. Where it is not configured, which is every
  scenario outside the first four Rules, the tailnet is the whole perimeter and
  nothing is in the way.

  What the tailnet side still costs, stated plainly so it is a choice and not an
  oversight: a request on the tailnet host is not attributed to a person, and an
  artifact link works for anyone who can reach that host. Who is on the tailnet
  is not yet established.

  Rule: With sign-in required, a request from outside the tailnet needs a valid one

    @stated
    Scenario Outline: A page is refused without a sign-in
      Given sign-in is required
      When I ask for "<page>" from outside the tailnet without signing in
      Then I am refused
      And nothing of the page is shown

      Examples:
        | page                    |
        | the recordings list     |
        | a recording detail view |
        | an artifact download    |
        | the system health view  |
        | the notifications page  |

    @edge-case
    Scenario Outline: A sign-in that does not check out is refused
      Given sign-in is required
      When I present a sign-in <kind> from outside the tailnet
      Then I am refused

      Examples:
        | kind                                |
        | issued for another application      |
        | issued by another team              |
        | that has expired                    |
        | signed by someone who is not Access |
        | that is not signed at all           |

    @stated
    Scenario: A valid sign-in is served
      Given sign-in is required
      When I present a valid sign-in for "pastor@reformation.example" from outside the tailnet
      Then the recordings list is served

    @edge-case
    Scenario: A claimed email address is not a sign-in
      Given sign-in is required
      When I ask for "the recordings list" from outside the tailnet claiming to be "pastor@reformation.example"
      Then I am refused
      # The address a request announces about itself is whatever the sender
      # typed. Only the address inside the signed statement is believed.

    @edge-case
    Scenario: The service cannot tell who is asking when Access's keys cannot be had
      Given sign-in is required
      And Access's signing keys cannot be fetched
      When I present a valid sign-in for "pastor@reformation.example" from outside the tailnet
      Then I am told sign-in cannot be checked right now
      And nothing of the page is shown

  Rule: The tailnet host is the one place that needs no sign-in

    @stated
    Scenario: A request on the tailnet host is served without a sign-in
      Given sign-in is required
      When I ask for "the recordings list" on the tailnet host
      Then the recordings list is served
      And nobody is named as signed in

    @edge-case
    Scenario Outline: The tailnet host's name arriving through Cloudflare is not the tailnet
      Given sign-in is required
      When I ask for "the recordings list" on the tailnet host having come through Cloudflare, shown by its <mark>
      Then I am refused

      Examples:
        | mark                           |
        | request identifier             |
        | record of the sender's address |

    @stated
    Scenario: The Recorder's webhook needs only its bearer token on the tailnet host
      Given sign-in is required
      When the Recorder sends a webhook on the tailnet host with its bearer token
      Then the webhook is accepted

    @edge-case
    Scenario: The tailnet host still refuses a webhook without its bearer token
      Given sign-in is required
      When the Recorder sends a webhook on the tailnet host without its bearer token
      Then the webhook is refused as unauthenticated

    @edge-case
    Scenario: A webhook from outside the tailnet needs a sign-in as well
      Given sign-in is required
      When the Recorder sends a webhook from outside the tailnet with its bearer token and no sign-in
      Then I am refused

    @edge-case
    Scenario: With no tailnet host named, nothing is exempt
      Given sign-in is required
      And no tailnet host is named
      When I ask for "the recordings list" on the host the tailnet host would have been
      Then I am refused

  Rule: Naming only one half of the sign-in check is a mistake the service will not start with

    @edge-case
    Scenario Outline: A half-configured sign-in
      When the service is started naming only <half> of its sign-in check
      Then it refuses to start
      And it says what is missing

      Examples:
        | half                   |
        | the Access team        |
        | the Access application |

  Rule: Who is signed in is shown, remembered and recorded

    @stated
    Scenario: The page says who is signed in
      Given sign-in is required
      When I present a valid sign-in for "pastor@reformation.example" from outside the tailnet
      Then the page names "pastor@reformation.example" as signed in

    @stated
    Scenario: A person is remembered once, however often they sign in
      Given sign-in is required
      When "pastor@reformation.example" visits on three separate occasions
      Then the system knows one person with that address

    @stated
    Scenario: An approval records the person who made it
      Given sign-in is required
      When "pastor@reformation.example" approves a Segment from outside the tailnet
      Then the approval is recorded against "pastor@reformation.example"

    @stated
    Scenario: An approval on the tailnet host is still the reviewer's
      Given sign-in is required
      When someone approves a Segment on the tailnet host
      Then the approval is recorded against "reviewer"
      And the system knows no one

  Rule: Without a sign-in configured, the network is the boundary

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

  Rule: Without a sign-in, actions are attributed to the system, not to a person

    @happy-path
    Scenario: An approval records what happened, not who did it
      When a Recording is approved
      Then the approval is recorded with its timestamp
      And the actor is recorded as "reviewer"
      # There is one reviewer. When there is more than one, this is the scenario
      # that has to change first, and `approval.feature` reads the actor from
      # here rather than assuming a name.

  Rule: Who an action is attributed to does not reshape what is recorded

    @assumption
    Scenario: The reviewer identity is a seam, not a constant
      Given the system records an actor on every human action
      Then adding real accounts changes who that actor is
      And it does not change what is recorded against it
