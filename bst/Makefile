
.PHONY: test

ENV_NAME=bst-env
BIN_DIR=$(CURDIR)/$(ENV_NAME)/bin

default: install

install:
	virtualenv $(CURDIR)/$(ENV_NAME)
	$(BIN_DIR)/pip install -r $(CURDIR)/requirements.txt
	$(BIN_DIR)/python $(CURDIR)/setup.py develop
	$(BIN_DIR)/pip install -e $(CURDIR)/.

clean:
	rm -rf $(CURDIR)/$(ENV_NAME)
	rm -rf $(CURDIR)/build
	rm -rf $(CURDIR)/dist
	rm -rf $(CURDIR)/src/zato_bst.egg-info
	find $(CURDIR) -name '*.pyc' -exec rm {} \;

test:
	$(MAKE) install
	$(BIN_DIR)/nosetests $(CURDIR)/test/zato/bst --with-coverage --cover-package=zato.bst --nocapture
	$(BIN_DIR)/flake8 $(CURDIR)/src/zato/bst --count
	$(BIN_DIR)/flake8 $(CURDIR)/test/zato/bst --count
