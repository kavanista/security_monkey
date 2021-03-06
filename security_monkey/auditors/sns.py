#     Copyright 2014 Netflix, Inc.
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
"""
.. module: security_monkey.auditors.sns
    :platform: Unix

.. version:: $$VERSION$$
.. moduleauthor:: Patrick Kelley <pkelley@netflix.com> @monkeysecurity

"""

from security_monkey.auditor import Auditor
from security_monkey.watchers.sns import SNS
from security_monkey.exceptions import InvalidARN
from security_monkey.exceptions import InvalidSourceOwner
from security_monkey.datastore import Account

import re


class SNSAuditor(Auditor):
    index = SNS.index
    i_am_singular = SNS.i_am_singular
    i_am_plural = SNS.i_am_plural

    def __init__(self, accounts=None, debug=False):
        super(SNSAuditor, self).__init__(accounts=accounts, debug=debug)

    def check_snstopicpolicy_empty(self, snsitem):
        """
        alert on empty SNS Policy
        """
        tag = "SNS Topic Policy is empty"
        severity = 1
        if snsitem.config.get('policy', {}) == {}:
            self.add_issue(severity, tag, snsitem, notes=None)

    def check_snstopicpolicy_crossaccount(self, snsitem):
        """
        alert on cross account access
        """
        policy = snsitem.config.get('policy', {})
        for statement in policy.get("Statement", []):
            account_numbers = []
            account_number = ''
            princ_aws = statement.get("Principal", {}) \
                .get("AWS", "error")
            if princ_aws == "*":
                account_number = statement.get("Condition", {}) \
                    .get("StringEquals", {}) \
                    .get("AWS:SourceOwner", None)
                if not account_number:
                    tag = "SNS Topic open to everyone"
                    notes = "An SNS policy where { 'Principal': { 'AWS': '*' } } must also have"
                    notes += " a {'Condition': {'StringEquals': { 'AWS:SourceOwner': '<ACCOUNT_NUMBER>' } } }"
                    notes += " or it is open to the world. In this case, anyone is allowed to perform "
                    notes += " this action(s): {}".format(statement.get("Action"))
                    self.add_issue(10, tag, snsitem, notes=notes)
                    continue
                else:
                    try:
                        account_numbers.append(str(account_number))
                    except ValueError:
                        raise InvalidSourceOwner(account_number)
            else:
                if isinstance(princ_aws, list):
                    for entry in princ_aws:
                        account_numbers.append(str(re.search('arn:aws:iam::([0-9-]+):', entry).group(1)))
                else:
                    try:
                        account_numbers.append(str(re.search('arn:aws:iam::([0-9-]+):', princ_aws).group(1)))
                    except:
                        raise InvalidARN(princ_aws)

            for account_number in account_numbers:
                self._check_account(account_number, snsitem, 'policy')

    def _check_account(self, account_number, snsitem, source):
        account = Account.query.filter(Account.number == account_number).first()
        account_name = None
        if account is not None:
            account_name = account.name

        src = account_name
        dst = snsitem.account
        if 'subscription' in source:
            src = snsitem.account
            dst = account_name

        notes = "SRC [{}] DST [{}]. Location: {}".format(src, dst, source)

        if not account_name:
            tag = "Unknown Cross Account Access"
            self.add_issue(10, tag, snsitem, notes=notes)
        elif account_name != snsitem.account and not account.third_party:
            tag = "Friendly Cross Account Access"
            self.add_issue(0, tag, snsitem, notes=notes)
        elif account_name != snsitem.account and account.third_party:
            tag = "Friendly Third Party Cross Account Access"
            self.add_issue(0, tag, snsitem, notes=notes)

    def check_subscriptions_crossaccount(self, snsitem):
        """
        "subscriptions": [
          {
               "Owner": "020202020202",
               "Endpoint": "someemail@example.com",
               "Protocol": "email",
               "TopicArn": "arn:aws:sns:us-east-1:020202020202:somesnstopic",
               "SubscriptionArn": "arn:aws:sns:us-east-1:020202020202:somesnstopic:..."
          }
        ]
        """
        subscriptions = snsitem.config.get('subscriptions', [])
        for subscription in subscriptions:
            source = '{0} subscription to {1}'.format(
                subscription.get('Protocol', None),
                subscription.get('Endpoint', None)
            )
            owner = subscription.get('Owner', None)
            self._check_account(owner, snsitem, source)