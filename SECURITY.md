# Security

Report vulnerabilities privately through GitHub's
[security advisories](https://github.com/MdaaaaO/observe-kit/security/advisories/new),
not in a public issue. Expect a first answer within a week.

Only the latest release is supported. The project publishes to PyPI with trusted publishing
(OIDC). No long-lived tokens exist that could leak.

`observed` writes argument values named in `fields` into log lines and events, and passes them to
your sink. Choose those fields as you would choose anything you log. What reaches a *notifier* is
limited by `NotifyPolicy`, which by default sends no context fields at all.
