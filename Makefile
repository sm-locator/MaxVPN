.PHONY: verify-routing

verify-routing:
	./scripts/verify_real_routing.sh "$(CLIENT_IP)"

.PHONY: build-sing-box-urltest
build-sing-box-urltest:
	@bash ./scripts/build_sing_box_v1_14_3.sh

.PHONY: test-docker

test-docker:
	bash ./scripts/test_isolated.sh $(PYTEST_ARGS)
