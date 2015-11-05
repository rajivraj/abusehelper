Files under contrib/ are (c) respective copyright holders if named in the specific file, everything else is current (c) by Codenomicon Ltd. Everything is licensed under MIT license (http://www.opensource.org/licenses/mit-license.php), see LICENSE.

## Important notice 2015-07-09

The contrib package in AbuseHelper will be migrated under abusehelper.bots package during 2015. This will require developers to change all references of abusehelper.contrib package to abusehelper.bots. All internal references within AbuseHelper have been updated to support the migration.

## What do I need to do?

All bots and modules abusehelper.contrib package will continue working until January 2016, but they will log deprecation errors to the logs. During this migration period, all references to abusehelper.contrib should be changed to point to abusehelper.bots package. Nothing else should be needed.

Some of the bots have also migrated to the new AbuseHelper community repository in: [https://bitbucket.org/ahcommunity/ahcommunity](https://bitbucket.org/ahcommunity/ahcommunity)

Following bots and modules have been migrated to ahcommunity repository and will cease working if used from abusehelper.contrib.

* contrib.arbor.atlassrf
* contrib.arbor.ssh
* contrib.bgp-xmpp.bgprankingbot
* contrib.csv2xmpp.csv2xmpp
* contrib.experts.bgpexpert
* contrib.experts.bgpquaggaexpert
* contrib.experts.iscpdnsexpert
* contrib.experts.iso3166expert
* contrib.experts.observerexpert
* contrib.experts.malwarehash
* contrib.experts.passivedns
* contrib.experts.rtexpert
* contrib.experts.sshkeyscan
* contrib.experts.url2domain
* contrib.iplist.iplist
* contrib.logcollector.logcollectorbot
* contrib.malwareblacklist.malwareblacklistbot
* contrib.mailextras.iodef
* contrib.mailextras.signingmailer
* contrib.urllistmailbot.urllistmailbot
* contrib.opencollab.crypto
* contrib.opencollab.downloader
* contrib.opencollab.virtualboxsandbox
* contrib.opencollab.webshot
* contrib.opencollab.wikicryptostartup
* contrib.opencollab.wikiruntime
* contrib.opencollab.wikistartup