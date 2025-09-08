#!/usr/bin/env python3
"""
Script to generate X.509 certificates for ATHENA-rods socket encryption
Needs to be run with root privileges.
Ondrej Chvala <ochvala@utexas.edu>
"""
import os
import subprocess
import re
# from arod_control import AUTH_ETC_PATH

# Path to CtrBox configuration, from home directory
AUTH_ETC_PATH: str = "git/athena_rods/etc"

# Path to Public Key Infrastructure of Certificate Authority for ATHENA-rod
PKI_PATH: str = '/etc/PKI-DT/ATHENA-rod/pki'

# CA for ATHENA-rod, derived from ROOT-CA, org: "First Austin Nuclear"
ATHENA_CA_CRT: str = '%s/ca-chain.crt' % PKI_PATH
ATHENA_CA_KEY: str = '%s/private/athena.key' % PKI_PATH


def load_vars(filepath):
    vars_dict = {}
    with open(filepath, 'r') as f:
        for line in f:
            # Match lines like: set_var VAR_NAME "value" or set_var VAR_NAME value
            match = re.match(r'set_var\s+(\S+)\s+"?([^"]+)"?', line.strip())
            if match:
                key, value = match.groups()
                # Try to convert numeric values to int
                if value.isdigit():
                    value = int(value)
                vars_dict[key] = value
    return vars_dict


# Load the vars from the file
vars_path = '%s/vars' % PKI_PATH
vars_loaded = load_vars(vars_path)


def run_command(cmd):
    """Run shell command and return output"""
    result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def create_subject_string(common_name):
    """Create a subject string for certificates using the loaded variables"""
    subject = f"/CN={common_name}"
    subject += f"/C={vars_loaded.get('EASYRSA_REQ_COUNTRY', 'US')}"
    subject += f"/ST={vars_loaded.get('EASYRSA_REQ_PROVINCE', 'Texas')}"
    subject += f"/L={vars_loaded.get('EASYRSA_REQ_CITY', 'Austin')}"
    subject += f"/O={vars_loaded.get('EASYRSA_REQ_ORG', 'First Austin Nuclear')}"
    subject += f"/OU={vars_loaded.get('EASYRSA_REQ_OU', 'Unit1 ATHENA')}"
    if 'EASYRSA_REQ_EMAIL' in vars_loaded:
        subject += f"/emailAddress={vars_loaded['EASYRSA_REQ_EMAIL']}"
    return subject


def main():
    # Create SSL certificates directory if it doesn't exist
    cert_dir = os.path.join(os.path.expanduser("~"), AUTH_ETC_PATH, "certs")
    os.makedirs(cert_dir, exist_ok=True)

    # Change to certificates directory
    os.chdir(cert_dir)

    # Copy the CA certificate for reference
    print("Copying CA certificate...")
    run_command(f"cp {ATHENA_CA_CRT} ca.crt")

    # Calculate days for certificate validity from loaded vars
    server_days = vars_loaded.get('EASYRSA_CERT_EXPIRE', 365)

    # Create server key and certificate signed by ATHENA-rod CA
    print("Generating server certificate...")
    # Generate a private key for the server
    run_command("openssl genrsa -out server.key 2048")
    # Create a CSR using the generated private key
    server_subject = create_subject_string("ctrlbox")
    run_command(f"openssl req -new -key server.key -out server.csr "
                f"-subj \"{server_subject}\"")
    # Sign the CSR with the CA certificate
    run_command(f"openssl x509 -req -days {server_days} -in server.csr "
                f"-CA {ATHENA_CA_CRT} -CAkey {ATHENA_CA_KEY} "
                f"-set_serial 01 -out server.crt "
                f"-{vars_loaded.get('EASYRSA_DIGEST', 'sha512')}")

    # Create client keys and certificates for instbox and visbox
    serial_number = 2
    for client in ["instbox", "visbox"]:
        print(f"Generating {client} certificate...")
        run_command(f"openssl genrsa -out {client}.key 2048")

        client_subject = create_subject_string(client)
        run_command(f"openssl req -new -key {client}.key -out {client}.csr "
                   f"-subj \"{client_subject}\"")

        run_command(f"openssl x509 -req -days {server_days} -in {client}.csr "
                   f"-CA {ATHENA_CA_CRT} -CAkey {ATHENA_CA_KEY} "
                   f"-set_serial 0{serial_number} -out {client}.crt "
                   f"-{vars_loaded.get('EASYRSA_DIGEST', 'sha512')}")
        serial_number += 1

    # Generate fingerprint for CA certificate and save to ca-chain.txt
    ca_fingerprint = run_command(f"openssl x509 -in {ATHENA_CA_CRT} -fingerprint -sha3-512 -noout")
    ca_fingerprint = ca_fingerprint.split('=')[1]

    # Save fingerprint to parent directory
    with open("../ca-chain.txt", "w") as f:
        f.write(ca_fingerprint)

    # Set appropriate permissions for the certificates and keys
    run_command("chmod 644 *.crt")
    run_command("chmod 600 *.key")

    print("Certificates generated successfully in:", cert_dir)
    print("CA fingerprint saved to:", os.path.expanduser("~/app/etc/ca-chain.txt"))
    print("Please update the configuration files to use these certificates.")


if __name__ == "__main__":
    main()
