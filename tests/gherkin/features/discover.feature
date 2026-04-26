Feature: Discover known hosts
  DeployBot should surface devices that are already known from SSH host history.

  Scenario: Discover lists hosts from a known_hosts fixture
    Given the environment variable "DEPLOYBOT_KNOWN_HOSTS" is "{project_root}/tests/gherkin/fixtures/known_hosts"
    Given the environment variable "DEPLOYBOT_DISABLE_ARP" is "1"
    When I run "deploybot discover"
    Then the command exits with code 0
    And the output contains "Discovered devices:"
    And the output contains "1. localhost (127.0.0.1) via known_hosts"
    And the output contains "2. 192.168.50.20 (192.168.50.20) via known_hosts"
