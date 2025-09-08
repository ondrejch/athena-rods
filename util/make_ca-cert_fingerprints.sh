#!/bin/bash
#
# Creates fingerprints of certificates
# Ondrej Chvala <ochvala@utexas.edu>

outd=/home/pi/app/etc
certs=(/etc/PKI-DT/root-ca/pki/ca.crt /etc/PKI-DT/ATHENA-rod/pki/ca-chain.crt)

for c in ${certs[@]}; do
	outf=$(basename $c | sed  s/crt/txt/g)
	fingerprint=$(openssl x509 -in $c -noout -fingerprint -sha3-512 | cut -d'=' -f2)
	echo $fingerprint > ${outd}/${outf}
	
#	rm -f ${outd}/${outf}
#	IFS=':' read -ra arr <<< $fingerprint
#	for i in "${arr[@]}"; do 
#		printf "%d " 0x$i >> ${outd}/${outf}
#	done 
#	echo >> ${outd}/${outf}


done


# openssl x509 -in /etc/PKI-DT/root-ca/pki/ca.crt -noout -fingerprint -sha256 > ~pi/app/fingerprint-ca.dat
# openssl x509 -in /etc/PKI-DT/ATHENA-rod/pki/ca-chain.crt -noout -fingerprint -sha256 > ~pi/app/fingerprint-ca-chain.dat

