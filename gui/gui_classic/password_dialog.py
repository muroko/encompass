#!/usr/bin/env python
#
# Electrum - lightweight Bitcoin client
# Copyright (C) 2013 ecdsa@github
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

from PyQt4.QtGui import *
from PyQt4.QtCore import *
from electrum.i18n import _
from qt_util import *



def make_password_dialog(self, wallet, msg):

    self.pw = QLineEdit()
    self.pw.setEchoMode(2)
    self.new_pw = QLineEdit()
    self.new_pw.setEchoMode(2)
    self.conf_pw = QLineEdit()
    self.conf_pw.setEchoMode(2)
    
    vbox = QVBoxLayout()
    vbox.addWidget(QLabel(msg))

    grid = QGridLayout()
    grid.setSpacing(8)
    grid.setColumnMinimumWidth(0,300)
    grid.setColumnStretch(1,1)

    if wallet.use_encryption:
        grid.addWidget(QLabel(_('Password')), 1, 0)
        grid.addWidget(self.pw, 1, 1)
        
    grid.addWidget(QLabel(_('New Password')), 2, 0)
    grid.addWidget(self.new_pw, 2, 1)

    grid.addWidget(QLabel(_('Confirm Password')), 3, 0)
    grid.addWidget(self.conf_pw, 3, 1)
    vbox.addLayout(grid)

    vbox.addStretch(1)
    vbox.addLayout(ok_cancel_buttons(self))
    self.setLayout(vbox) 


def run_password_dialog(self, wallet, parent):
        
    if not wallet.seed:
        QMessageBox.information(parent, _('Error'), _('No seed'), _('OK'))
        return

    if not self.exec_(): return

    password = unicode(self.pw.text()) if wallet.use_encryption else None
    new_password = unicode(self.new_pw.text())
    new_password2 = unicode(self.conf_pw.text())

    try:
        seed = wallet.decode_seed(password)
    except:
        QMessageBox.warning(parent, _('Error'), _('Incorrect Password'), _('OK'))
        return

    if new_password != new_password2:
        QMessageBox.warning(parent, _('Error'), _('Passwords do not match'), _('OK'))
        self.run() # Retry

    try:
        wallet.update_password(seed, password, new_password)
    except:
        QMessageBox.warning(parent, _('Error'), _('Failed to update password'), _('OK'))
        return

    if new_password:
        QMessageBox.information(parent, _('Success'), _('Password was updated successfully'), _('OK'))
    else:
        QMessageBox.information(parent, _('Success'), _('This wallet is not encrypted'), _('OK'))




class PasswordDialog(QDialog):

    def __init__(self, wallet, parent):
        QDialog.__init__(self, parent)
        self.setModal(1)
        self.wallet = wallet
        self.parent = parent
        msg = (_('Your wallet is encrypted. Use this dialog to change your password.')+'\n'\
               +_('To disable wallet encryption, enter an empty new password.')) \
               if wallet.use_encryption else _('Your wallet keys are not encrypted')
        make_password_dialog(self, wallet, msg)


    def run(self):
        run_password_dialog(self, self.wallet, self.parent)


