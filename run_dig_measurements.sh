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
		cd /home/ubuntu/dnsproxy
	
		https_upstream="${upstream}/dns-query"
		
		timestamp="`date "+%Y-%m-%d_%H_%M_%S"`"
		echo "starting tcpdump"
		#start tcpdump and sleep for 5s because apparently it needs to initialize
		tcpdump -U -i any -w /home/ubuntu/dns-measurements-dig/capture-${upstream}-${timestamp}.pcap &
		sleep 5

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

			
		
			sleep 1
			echo "starting dnsproxy"
			./dnsproxy -u ${resolver} -v --insecure --ipv6-disabled -l "127.0.0.2" >& /home/ubuntu/dns-measurements-dig/dnsproxy.log &
			dnsproxyPID=$!
	
			# measurements
			sleep 1
			cd /home/ubuntu/dns-measurements-dig
			python3 dig_measurement_metrics.py $p $upstream $dnsproxyPID $timestamp
			
			
			sleep 1
			echo "killing dnsproxy"
			kill -SIGTERM $dnsproxyPID
			
			echo "cleaning up logs"
			rm dnsproxy.log
			cd /home/ubuntu/dnsproxy

		done
		#https://askubuntu.com/a/746061
		tcpdumpPID=$(ps -e | pgrep tcpdump)  
		echo "killing tcpdump"
		sleep 5
		kill -2 $tcpdumpPID

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
