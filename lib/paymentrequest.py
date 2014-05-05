import hashlib
import httplib
import os.path
import re
import sys
import threading
import time
import traceback
import urllib2

try:
    import paymentrequest_pb2
except:
    print "protoc --proto_path=lib/ --python_out=lib/ lib/paymentrequest.proto"
    sys.exit(1)

import urlparse
import requests
from M2Crypto import X509

from bitcoin import is_valid
import urlparse

import transaction

REQUEST_HEADERS = {'Accept': 'application/bitcoin-paymentrequest', 'User-Agent': 'Electrum'}
ACK_HEADERS = {'Content-Type':'application/bitcoin-payment','Accept':'application/bitcoin-paymentack','User-Agent':'Electrum'}

class PaymentRequest:

    def __init__(self):
        self.ca_path = os.path.expanduser("~/.electrum/ca/ca-bundle.crt")
        self.ca_list = {}
        try:
            with open(self.ca_path, 'r') as ca_f:
                c = ""
                for line in ca_f:
                    if line == "-----BEGIN CERTIFICATE-----\n":
                        c = line
                    else:
                        c += line
                    if line == "-----END CERTIFICATE-----\n":
                        x = X509.load_cert_string(c)
                        self.ca_list[x.get_fingerprint()] = x
        except Exception:
            print "ERROR: Could not open %s"%self.ca_path
            print "ca-bundle.crt file should be placed in ~/.electrum/ca/ca-bundle.crt"
            print "Documentation on how to download or create the file here: http://curl.haxx.se/docs/caextract.html"
            print "Payment will continue with manual verification."



    def verify(self, url):

        u = urlparse.urlparse(urllib2.unquote(url))
        self.domain = u.netloc

        connection = httplib.HTTPConnection(u.netloc) if u.scheme == 'http' else httplib.HTTPSConnection(u.netloc)
        connection.request("GET",u.geturl(), headers=REQUEST_HEADERS)
        resp = connection.getresponse()

        r = resp.read()
        paymntreq = paymentrequest_pb2.PaymentRequest()
        paymntreq.ParseFromString(r)

        sig = paymntreq.signature

        cert = paymentrequest_pb2.X509Certificates()
        cert.ParseFromString(paymntreq.pki_data)
        cert_num = len(cert.certificate)

        x509_1 = X509.load_cert_der_string(cert.certificate[0])
        if self.domain != x509_1.get_subject().CN:
            ###TODO: check for subject alt names
            ###       check for wildcards
            print "ERROR: Certificate Subject Domain Mismatch"
            print self.domain, x509_1.get_subject().CN
            #return

        x509 = []
        CA_OU = ''

        if cert_num > 1:
            for i in range(cert_num - 1):
                x509.append(X509.load_cert_der_string(cert.certificate[i+1]))
                if x509[i].check_ca() == 0:
                    print "ERROR: Supplied CA Certificate Error"
                    return
            for i in range(cert_num - 1):
                if i == 0:
                    if x509_1.verify(x509[i].get_pubkey()) != 1:
                        print "ERROR: Certificate not Signed by Provided CA Certificate Chain"
                        return
                else:
                    if x509[i-1].verify(x509[i].get_pubkey()) != 1:
                        print "ERROR: CA Certificate not Signed by Provided CA Certificate Chain"
                        return

            supplied_CA_fingerprint = x509[cert_num-2].get_fingerprint()
            supplied_CA_CN = x509[cert_num-2].get_subject().CN
            CA_match = False

            x = self.ca_list.get(supplied_CA_fingerprint)
            if x:
                CA_OU = x.get_subject().OU
                CA_match = True
                if x.get_subject().CN != supplied_CA_CN:
                    print "ERROR: Trusted CA CN Mismatch; however CA has trusted fingerprint"
                    print "Payment will continue with manual verification."
            else:
                print "ERROR: Supplied CA Not Found in Trusted CA Store."
                print "Payment will continue with manual verification."
        else:
            print "ERROR: CA Certificate Chain Not Provided by Payment Processor"
            return False

        paymntreq.signature = ''
        s = paymntreq.SerializeToString()
        pubkey_1 = x509_1.get_pubkey()

        if paymntreq.pki_type == "x509+sha256":
            pubkey_1.reset_context(md="sha256")
        elif paymntreq.pki_type == "x509+sha1":
            pubkey_1.reset_context(md="sha1")
        else:
            print "ERROR: Unsupported PKI Type for Message Signature"
            return False

        pubkey_1.verify_init()
        pubkey_1.verify_update(s)
        if pubkey_1.verify_final(sig) != 1:
            print "ERROR: Invalid Signature for Payment Request Data"
            return False

        ### SIG Verified

        self.payment_details = pay_det = paymentrequest_pb2.PaymentDetails()
        pay_det.ParseFromString(paymntreq.serialized_payment_details)

        if pay_det.expires and pay_det.expires < int(time.time()):
            print "ERROR: Payment Request has Expired."
            return False

        self.outputs = []
        for o in pay_det.outputs:
            addr = transaction.get_address_from_output_script(o.script)[1]
            self.outputs.append( (addr, o.amount) )

        if CA_match:
            print 'Signed By Trusted CA: ', CA_OU

        return True



    def send_ack(self, raw_tx, refund_addr):

        pay_det = self.payment_details
        if pay_det.payment_url:
            paymnt = paymentrequest_pb2.Payment()

            paymnt.merchant_data = pay_det.merchant_data
            paymnt.transactions.append(raw_tx)

            ref_out = paymnt.refund_to.add()
            ref_out.script = transaction.Transaction.pay_script(refund_addr)
            paymnt.memo = "Paid using Electrum"
            pm = paymnt.SerializeToString()

            payurl = urlparse.urlparse(pay_det.payment_url)
            try:
                r = requests.post(payurl.geturl(), data=pm, headers=ACK_HEADERS, verify=self.ca_path)
            except requests.exceptions.SSLError:
                print "Payment Message/PaymentACK verify Failed"
                try:
                    r = requests.post(payurl.geturl(), data=pm, headers=ACK_HEADERS, verify=False)
                except Exception as e:
                    print "Payment Message/PaymentACK Failed"
                    print e
                    return
            try:
                paymntack = paymentrequest_pb2.PaymentACK()
                paymntack.ParseFromString(r.content)
                print "PaymentACK message received: %s" % paymntack.memo
            except Exception:
                print "PaymentACK could not be processed. Payment was sent; please manually verify that payment was received."


uri = "bitcoin:mpu3yTLdqA1BgGtFUwkVJmhnU3q5afaFkf?r=https%3A%2F%2Fbitcoincore.org%2F%7Egavin%2Ff.php%3Fh%3D26c19879d44c3891214e7897797b9160&amount=1"
url = "https%3A%2F%2Fbitcoincore.org%2F%7Egavin%2Ff.php%3Fh%3D26c19879d44c3891214e7897797b9160"

#uri = "bitcoin:1m9Lw2pFCe6Hs7xUuo9fMJCzEwQNdCo5e?amount=0.0012&r=https%3A%2F%2Fbitpay.com%2Fi%2F8XNDiQU92H2whNG4j8hZ5M"
#url = "https%3A%2F%2Fbitpay.com%2Fi%2F8XNDiQU92H2whNG4j8hZ5M"


if __name__ == "__main__":

    pr = PaymentRequest()
    if not pr.verify(url):
        sys.exit(1)

    print 'Payment Request Verified Domain: ', pr.domain
    print 'outputs', pr.outputs
    print 'Payment Memo: ', pr.payment_details.memo

    tx = "blah"
    pr.send_ack(tx, "1vXAXUnGitimzinpXrqDWVU4tyAAQ34RA")
