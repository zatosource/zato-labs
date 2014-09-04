
#SHELL := /bin/bash
.PHONY: test

ENV_NAME=env-zato
ENV_DIR=$(CURDIR)/$(ENV_NAME)
BIN_DIR=$(ENV_DIR)/bin

default: install

# ################################################################################################################################
#
# Note the sed invocation in `install` to get around the issue with package_dir
# https://bitbucket.org/tarek/distribute/issue/177/setuppy-develop-doesnt-support-package_dir
# https://bitbucket.org/pypa/setuptools/issue/230
#
# ################################################################################################################################

install:
	virtualenv $(CURDIR)/$(ENV_NAME)
	$(BIN_DIR)/pip install -r $(CURDIR)/requirements.txt
	$(BIN_DIR)/pip install -e $(CURDIR)/zato-cli
	sed -i -e's@zato-cli@zato-cli/src@' $(ENV_DIR)/lib/python2.7/site-packages/easy-install.pth

clean:
	rm -rf $(CURDIR)/$(ENV_NAME)
	rm -rf $(CURDIR)/zato-cli/zato_cli.egg-info
	rm -rf $(CURDIR)/zato-cli/build
	find $(CURDIR) -name '*.c' -exec rm {} \;
	find $(CURDIR) -name '*.egg-info' -exec rm {} \;
	find $(CURDIR) -name '*.pyc' -exec rm {} \;
	find $(CURDIR) -name '*.so' -exec rm {} \;

test:
	$(BIN_DIR)/nosetests $(CURDIR)/zato-* --with-coverage --cover-package=zato --nocapture
	$(BIN_DIR)/flake8 $(CURDIR)/zato-* --count
