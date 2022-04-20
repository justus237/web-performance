#!/bin/bash

if [[ $EUID -ne 0 ]]; then
    echo "$0 is not running as root. Try using sudo."
    exit 2
fi
SECONDS=0
#if [[ $EUID -ne 0 ]]; then
#    sudo "$0" "$@"
#    exit $?
#fi
echo "starting measurement process..."
date


# increase UDP receive buffer size
sysctl -w net.core.rmem_max=25000000
# stop systemd-resolved and edit resolv.conf
systemctl stop systemd-resolved
systemctl disable systemd-resolved
echo "nameserver 127.0.0.2" | tee /etc/resolv.conf
# disable ipv6
sysctl -w net.ipv6.conf.all.disable_ipv6=1
sysctl -w net.ipv6.conf.default.disable_ipv6=1
sysctl -w net.ipv6.conf.lo.disable_ipv6=1

declare -a protocols=("tls" "https" "quic" "tcp" "udp")


while read upstream; do
	qport=$(echo ${upstream} | cut -d: -f2)
  	upstream=$(echo ${upstream} | cut -d: -f1)
  	# skip server if it is unreachable
	ping -c 1 ${upstream} 2>&1 >/dev/null ;
	ping_code=$?
	if [ $ping_code = 0 ]
	then
		timestamp="`date "+%Y-%m-%d_%H_%M_%S"`"
		cd /home/ubuntu/dnsproxy
	
		https_upstream="${upstream}/dns-query"
		

		for p in "${protocols[@]}"
		do
			echo $p

			if [ $p = "udp" ]
			then
				resolver="${upstream}"
			elif [ $p = "https" ]
			then
				resolver="${p}://${https_upstream}"
			elif [ $p = "quic" ]
			then
				if [ $qport = "8853" ]
				then
					resolver="quic://${upstream}:8853"
				elif [ $qport = "853" ]
				then
					resolver="quic://${upstream}:853"
				else
					resolver="quic://${upstream}:784"
				fi
			else
				resolver="${p}://${upstream}"
			fi
			echo "cache warming for ${resolver} ${timestamp}"

			echo "starting tcpdump"
			#start tcpdump and sleep for 5s because apparently it needs to initialize
			tcpdump -U -i any -w /home/ubuntu/dns-measurements-dig/cache-warming/capture-${p}-${upstream}-${timestamp}.pcap &
			sleep 5
		
			echo "starting dnsproxy"
			./dnsproxy -u ${resolver} -v --insecure --ipv6-disabled -l "127.0.0.2" >& /home/ubuntu/dnsproxy/dnsproxy.log &
			dnsproxyPID=$!
			sleep 3
			
			echo "running dns query"
			dig @127.0.0.2 test.com > /home/ubuntu/dns-measurements-dig/cache-warming/dig-${p}-${upstream}-${timestamp}.log

			
			echo "moving cache warming capture and logs"
			cp dnsproxy.log /home/ubuntu/dns-measurements-dig/cache-warming/dnsproxy-${p}-${upstream}-${timestamp}.log
			sleep 0.5
			truncate -s0 dnsproxy.log
			#if [ $p = "quic" ]
			#then
			#	cp qlogs.txt /home/ubuntu/dns-measurements-dig/cache-warming/dnsproxy-qlog-${upstream}-${timestamp}.txt
			#	sleep 0.5
			#	truncate -s0 qlogs.txt
			#fi

			echo "stopping and restarting tcpdump"
			tcpdumpPID=$(ps -e | pgrep tcpdump)  
			echo "killing tcpdump ${tcpdumpPID}"
			sleep 5
			kill -2 $tcpdumpPID
			sleep 1
			tcpdump -U -i any -w /home/ubuntu/dns-measurements-dig/session-resumption/capture-${p}-${upstream}-${timestamp}.pcap &
			sleep 5

			echo "dnsproxy reset ${dnsproxyPID}"
			kill -SIGUSR1 $dnsproxyPID

			echo "measurement for ${resolver} ${timestamp}"
			sleep 1
			dig @127.0.0.2 test.com > /home/ubuntu/dns-measurements-dig/session-resumption/dig-${p}-${upstream}-${timestamp}.log


			#https://askubuntu.com/a/746061
			tcpdumpPID=$(ps -e | pgrep tcpdump)  
			echo "killing tcpdump ${tcpdumpPID}"
			sleep 5
			kill -2 $tcpdumpPID
			
			sleep 1
			echo "killing dnsproxy"
			kill -SIGTERM $dnsproxyPID
			
			echo "cleaning up logs"
			cp dnsproxy.log /home/ubuntu/dns-measurements-dig/session-resumption/dnsproxy-${p}-${upstream}-${timestamp}.log
			sleep 0.5
			rm /home/ubuntu/dnsproxy/dnsproxy.log
			
			if [ $p = "quic" ]
			then
				cp qlogs.txt /home/ubuntu/dns-measurements-dig/session-resumption/dnsproxy-qlog-${upstream}-${timestamp}.txt
				sleep 0.5
				rm /home/ubuntu/dnsproxy/qlogs.txt
			fi
			cd /home/ubuntu/dnsproxy

		done
	else
		echo "${upstream} not reachable"
	fi
done < /home/ubuntu/dns-measurements-dig/servers.txt



# restart systemd-resolved
systemctl enable systemd-resolved
systemctl start systemd-resolved

date
# https://unix.stackexchange.com/a/340156
ELAPSED="Elapsed: $(($SECONDS / 3600))hrs $((($SECONDS / 60) % 60))min $(($SECONDS % 60))sec"
echo $ELAPSED
