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
  stays off Cloudflare, and the Recorder's webhook, which reaches the service
  there, answers to its bearer token alone.

  Settled 2026-10-26, later the same day, changing the tailnet host: it is no
  longer open. Every request to the service carries a real identity, so that who
  took an action is always a person the system knows. On the tailnet host a person
  signs in with an email address and a password the owner gave them, and is the
  same person as the one Cloudflare Access vouches for under that address: one
  record, found by the lower-cased address. What is wanted there is attribution,
  not a stronger perimeter, so the sign-in is kept simple: no self-service
  sign-up, no password reset, and the owner makes people and sets their
  passwords from the command line on the server.

  The sign-in is remembered by the browser. A form that changes something
  (approving, skipping, adjusting a cut) is protected from another site by that
  memory not being sent along with a request another site causes, rather than by a
  token in each form. The sign-in and sign-out forms are additionally refused
  when they are submitted from another site. The memory is only ever sent over a
  secure connection, whatever the request or a proxy claims about its own: both
  ways in are secure connections in use, and a scheme guessed from what a client
  can send is not something to rest that on.

  Settled 2026-10-26, a third time: who is signed in also decides what they may
  do. "I would like to have a read-only mode for this as well, where a user can
  only download and view recordings and can't actually make edits. If we design
  for both now, that makes it easy: they just don't get the edit button." Asked
  what a person signing in for the first time may do, the owner chose "View only
  until promoted": everyone is a viewer until the owner makes them a reviewer
  with a command on the server.

  Sign-in is a deployment setting. Where it is not configured, which is every
  scenario that does not begin by saying sign-in is required, the tailnet is the
  whole perimeter and nothing is in the way.

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

    @edge-case
    Scenario: A sign-in remembered from the tailnet host is not a sign-in from outside it
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      And I have signed in on the tailnet host as "pastor@reformation.example" with "correct horse battery"
      When I ask for "the recordings list" from outside the tailnet carrying that sign-in
      Then I am refused

    @edge-case
    Scenario: A valid Cloudflare sign-in outranks a remembered password sign-in
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      And I have signed in on the tailnet host as "pastor@reformation.example" with "correct horse battery"
      When I present a valid sign-in for "elder@reformation.example" from outside the tailnet carrying that sign-in
      Then the page names "elder@reformation.example" as signed in

  Rule: On the tailnet host a person signs in with an email address and a password

    @stated
    Scenario Outline: A page on the tailnet host sends a browser that has not signed in to the sign-in page
      Given sign-in is required
      When I ask for "<page>" on the tailnet host in a browser without signing in
      Then I am sent to the sign-in page
      And nothing of the page is shown

      Examples:
        | page                    |
        | the recordings list     |
        | a recording detail view |
        | the notifications page  |

    @edge-case
    Scenario Outline: A request that is not from a browser is refused rather than sent to the sign-in page
      Given sign-in is required
      When I ask for "<page>" on the tailnet host without signing in
      Then I am refused
      And nothing of the page is shown

      Examples:
        | page                   |
        | the system health view |
        | an artifact download   |
        | the recordings list    |

    @edge-case
    Scenario: A change submitted from a browser that has not signed in is sent to the sign-in page
      Given sign-in is required
      When a browser that has not signed in approves a Segment on the tailnet host
      Then I am sent to the sign-in page
      And no approval is recorded

    @edge-case
    Scenario: A change from a client that has not signed in is refused
      Given sign-in is required
      When someone approves a Segment on the tailnet host
      Then I am refused
      And no approval is recorded

    @stated
    Scenario: The sign-in page can be reached without signing in
      Given sign-in is required
      When I ask for "the sign-in page" on the tailnet host without signing in
      Then the sign-in page is shown

    @edge-case
    Scenario: The sign-in page's own styling can be reached without signing in
      Given sign-in is required
      When I ask for "the sign-in page's styling" on the tailnet host without signing in
      Then the styling is served

    @stated
    Scenario: The right email address and password sign a person in
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      When I sign in on the tailnet host as "pastor@reformation.example" with "correct horse battery"
      Then I am taken to the recordings list
      And the page names "pastor@reformation.example" as signed in

    @edge-case
    Scenario: The email address is matched without regard to case
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      When I sign in on the tailnet host as "  Pastor@Reformation.Example " with "correct horse battery"
      Then I am taken to the recordings list
      And the page names "pastor@reformation.example" as signed in

    @stated
    Scenario Outline: A person who has signed in is served every page
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      And I have signed in on the tailnet host as "pastor@reformation.example" with "correct horse battery"
      When I ask for "<page>" on the tailnet host
      Then I see the page
      And I am not asked to sign in

      Examples:
        | page                    |
        | the recordings list     |
        | a recording detail view |
        | the notifications page  |
        | the system health view  |

    @stated
    Scenario: A person who was sent to sign in is returned to the page they asked for
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      When I ask for "a recording detail view" on the tailnet host in a browser without signing in
      And I sign in as "pastor@reformation.example" with "correct horse battery" on the sign-in page I was sent to
      Then I am taken to the page I first asked for

    @edge-case
    Scenario Outline: A sign-in cannot send a person to another site
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      When I sign in on the tailnet host as "pastor@reformation.example" with "correct horse battery" asking to be taken to "<destination>"
      Then I am taken to the recordings list

      Examples:
        | destination            |
        | https://evil.example/  |
        | //evil.example/        |
        | data:text/html,hello   |

    @stated
    Scenario: Signing out ends the sign-in
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      And I have signed in on the tailnet host as "pastor@reformation.example" with "correct horse battery"
      When I sign out
      And I ask for "the recordings list" on the tailnet host in a browser
      Then I am sent to the sign-in page

    @edge-case
    Scenario: A sign-in attempt that came through Cloudflare is refused
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      When I sign in on the tailnet host as "pastor@reformation.example" with "correct horse battery" having come through Cloudflare
      Then I am refused

  Rule: A person is told nothing a stranger could use about who has an account

    @edge-case
    Scenario Outline: A wrong password and an unknown address are answered alike
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      When I sign in on the tailnet host as "<email>" with "<password>"
      Then the sign-in page is shown again
      And it says only that the email address or password is not right
      And nobody is named as signed in

      Examples:
        | email                      | password              |
        | pastor@reformation.example | not the password      |
        | nobody@reformation.example | not the password      |
        | nobody@reformation.example | correct horse battery |

    @edge-case
    Scenario: The two answers cannot be told apart
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      When I sign in on the tailnet host as "pastor@reformation.example" with "not the password"
      And I sign in on the tailnet host as "nobody@reformation.example" with "not the password"
      Then the two answers are identical

    @edge-case
    Scenario: A person who has only ever come through Cloudflare has no password to sign in with
      Given sign-in is required
      And "elder@reformation.example" has only signed in through Cloudflare
      When I sign in on the tailnet host as "elder@reformation.example" with "anything at all"
      Then the sign-in page is shown again
      And nobody is named as signed in

    @edge-case
    Scenario: A blank password is refused
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      When I sign in on the tailnet host as "pastor@reformation.example" with ""
      Then the sign-in page is shown again

    @edge-case
    Scenario: Repeated wrong passwords hold a person off for a while, even for the right one
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      When someone gives a wrong password for "pastor@reformation.example" 5 times on the tailnet host
      And I sign in on the tailnet host as "pastor@reformation.example" with "correct horse battery"
      Then I am told to wait before trying again
      And nobody is named as signed in

    @edge-case
    Scenario: The wait ends
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      When someone gives a wrong password for "pastor@reformation.example" 5 times on the tailnet host
      And 2 minutes pass
      And I sign in on the tailnet host as "pastor@reformation.example" with "correct horse battery"
      Then I am taken to the recordings list

    @edge-case
    Scenario: One machine trying many addresses is held off though no address was tried often
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      When someone tries 20 different email addresses from one machine on the tailnet host
      And I sign in on the tailnet host as "pastor@reformation.example" with "correct horse battery"
      Then I am told to wait before trying again

    @edge-case
    Scenario: A sign-in submitted from another site is refused
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      When a page on another site submits "pastor@reformation.example" with "correct horse battery" to the tailnet host's sign-in
      Then the submission is refused
      When I ask for "the recordings list" on the tailnet host in a browser
      Then I am sent to the sign-in page

    @edge-case
    Scenario: A sign-out submitted from another site is refused
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      And I have signed in on the tailnet host as "pastor@reformation.example" with "correct horse battery"
      When a page on another site asks to sign me out
      Then the submission is refused
      When I ask for "the recordings list" on the tailnet host in a browser
      Then I see the page

  Rule: A person can sign in on the tailnet host only with a password the owner gave them

    @stated
    Scenario: The owner adds a person with a password
      Given sign-in is required
      When the owner adds "elder@reformation.example" with the password "an elder's passphrase"
      And I sign in on the tailnet host as "elder@reformation.example" with "an elder's passphrase"
      Then I am taken to the recordings list
      And the page names "elder@reformation.example" as signed in

    @stated
    Scenario: The owner changes a password and the old one stops working
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      When the owner gives "pastor@reformation.example" the new password "a brand new passphrase"
      And I sign in on the tailnet host as "pastor@reformation.example" with "correct horse battery"
      Then the sign-in page is shown again

    @stated
    Scenario: Changing a password ends the sign-ins made with the old one
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      And I have signed in on the tailnet host as "pastor@reformation.example" with "correct horse battery"
      When the owner gives "pastor@reformation.example" the new password "a brand new passphrase"
      And I ask for "the recordings list" on the tailnet host in a browser
      Then I am sent to the sign-in page

    @edge-case
    Scenario: A password too short to be worth having is not accepted
      Given sign-in is required
      When the owner tries to add "elder@reformation.example" with the password "short"
      Then the owner is told the password is too short
      And the system knows no one

    @stated
    Scenario: A password is kept only as a salted hash
      Given sign-in is required
      And "pastor@reformation.example" and "elder@reformation.example" have both been given the password "correct horse battery"
      Then the system holds a different record of each
      And neither record contains the password

    @stated
    Scenario: The same person is one person however they signed in
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      When I present a valid sign-in for "pastor@reformation.example" from outside the tailnet
      And I sign in on the tailnet host as "pastor@reformation.example" with "correct horse battery"
      Then the system knows one person with that address

  Rule: A password sign-in is good on the tailnet host and nowhere else

    @edge-case
    Scenario Outline: The tailnet host's name arriving through Cloudflare is not the tailnet
      Given sign-in is required
      When I ask for "the recordings list" on the tailnet host having come through Cloudflare, shown by its <mark>
      Then I am refused

      Examples:
        | mark                           |
        | request identifier             |
        | record of the sender's address |

    @edge-case
    Scenario Outline: A password sign-in is not honoured when the request came through Cloudflare
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      And I have signed in on the tailnet host as "pastor@reformation.example" with "correct horse battery"
      When I ask for "the recordings list" on the tailnet host, carrying that sign-in, having come through Cloudflare, shown by its <mark>
      Then I am refused

      Examples:
        | mark                           |
        | request identifier             |
        | record of the sender's address |

    @edge-case
    Scenario: With no tailnet host named, no password sign-in is taken
      Given sign-in is required
      And no tailnet host is named
      When I ask for "the recordings list" on the host the tailnet host would have been
      Then I am refused

    @edge-case
    Scenario: With no tailnet host named, there is no sign-in page
      Given sign-in is required
      And no tailnet host is named
      When I ask for "the sign-in page" on the host the tailnet host would have been
      Then I am refused

    @edge-case
    Scenario: The sign-in page is not offered from outside the tailnet
      Given sign-in is required
      When I ask for "the sign-in page" from outside the tailnet without signing in
      Then I am refused

  Rule: The Recorder's webhook answers to its bearer token alone

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
      And I am not sent to the sign-in page

    @edge-case
    Scenario: A webhook from outside the tailnet needs a sign-in as well
      Given sign-in is required
      When the Recorder sends a webhook from outside the tailnet with its bearer token and no sign-in
      Then I am refused

  Rule: The sign-in is remembered as narrowly as a browser allows

    @edge-case
    Scenario: The cookie always carries Secure, HttpOnly, SameSite=Lax and no Domain
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      When I sign in on the tailnet host as "pastor@reformation.example" with "correct horse battery"
      Then the browser is told to keep the sign-in for the tailnet host alone
      And the browser is told not to send the sign-in with a request another site causes
      And the browser is told to keep the sign-in from a page's scripts
      And the browser is told to send the sign-in only over a secure connection

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
      And "pastor@reformation.example" is a reviewer
      When "pastor@reformation.example" approves a Segment from outside the tailnet
      Then the approval is recorded against "pastor@reformation.example"

    @stated
    Scenario: An approval on the tailnet host records the person who signed in there
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      And "pastor@reformation.example" is a reviewer
      And I have signed in on the tailnet host as "pastor@reformation.example" with "correct horse battery"
      When I approve a Segment on the tailnet host
      Then the approval is recorded against "pastor@reformation.example"

    @stated
    Scenario: A Segment skipped on the tailnet host records the person who signed in there
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      And "pastor@reformation.example" is a reviewer
      And I have signed in on the tailnet host as "pastor@reformation.example" with "correct horse battery"
      When I skip a Segment on the tailnet host
      Then the skip is recorded against "pastor@reformation.example"

    @stated
    Scenario: A person signed in with a password can sign out
      Given sign-in is required
      And "pastor@reformation.example" has the password "correct horse battery"
      When I sign in on the tailnet host as "pastor@reformation.example" with "correct horse battery"
      Then the page offers to sign out

    @edge-case
    Scenario: A person signed in through Cloudflare is not offered a sign-out the service cannot honour
      Given sign-in is required
      When I present a valid sign-in for "pastor@reformation.example" from outside the tailnet
      Then the page does not offer to sign out

  Rule: A person may look until the owner makes them a reviewer

    @stated
    Scenario: A person signing in for the first time can only look
      Given sign-in is required
      When I present a valid sign-in for "visitor@reformation.example" from outside the tailnet
      Then the page says I can look but not change anything

    @stated
    Scenario: A person the owner adds can only look until made a reviewer
      Given sign-in is required
      When the owner adds "elder@reformation.example" with the password "an elder's passphrase"
      And I sign in on the tailnet host as "elder@reformation.example" with "an elder's passphrase"
      Then the page says I can look but not change anything

    @stated
    Scenario: The owner makes a person a reviewer
      Given sign-in is required
      And "elder@reformation.example" has the password "an elder's passphrase"
      When the owner makes "elder@reformation.example" a reviewer
      And I sign in on the tailnet host as "elder@reformation.example" with "an elder's passphrase"
      And I approve a Segment on the tailnet host
      Then the owner is told "elder@reformation.example" is now a reviewer
      And the approval is recorded against "elder@reformation.example"

    @stated
    Scenario: A viewer sees the cut and nothing that would change it
      Given sign-in is required
      And the seekable preview has been rendered
      And "visitor@reformation.example" has the password "correct horse battery"
      And I have signed in on the tailnet host as "visitor@reformation.example" with "correct horse battery"
      When I open a proposed Segment on the tailnet host
      Then the page offers the preview of the cut and each of its seams
      And the page offers no switch to editing, no approval, no skip and no recording-level action

    @stated
    Scenario: A viewer can download what is finished
      Given sign-in is required
      And a Segment in state "complete" from a Recording dated "2026-08-23"
      And "visitor@reformation.example" has the password "correct horse battery"
      And I have signed in on the tailnet host as "visitor@reformation.example" with "correct horse battery"
      When I open the finished Segment on the tailnet host
      Then the page offers its MP3 and the original recording to download
      And the MP3 it offers is served to me

    @stated
    Scenario Outline: A change a viewer asks for is refused
      # Hiding the controls is the courtesy; refusing the request is the rule.
      Given sign-in is required
      And "visitor@reformation.example" has the password "correct horse battery"
      And I have signed in on the tailnet host as "visitor@reformation.example" with "correct horse battery"
      When I ask to <change> on the tailnet host
      Then I am refused because I can only look
      And nothing about the Recording has changed

      Examples:
        | change                    |
        | approve a Segment         |
        | skip a Segment            |
        | move the punch-in         |
        | remove a span             |
        | reclassify a Segment      |
        | rename the Recording      |
        | discard the Recording     |
        | re-run analysis           |

  Rule: Without a sign-in configured, the network is the boundary

    @happy-path
    Scenario: Without a sign-in, the person at the browser can review
      # Nobody is identified, so nobody can be a viewer; actions are still
      # recorded as "reviewer" (the next Rule).
      Given I am on the tailnet
      When I open a proposed Segment
      Then the page offers a switch to editing and the approval

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

    @edge-case
    Scenario: There is no sign-in page to reach
      When I visit "the sign-in page"
      Then there is no such page

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
