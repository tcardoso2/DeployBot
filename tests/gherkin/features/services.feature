Feature: List remote services
  DeployBot should detect known remote services on a discovered server.

  Scenario: Services shows ngrok availability
    Given the environment variable "DEPLOYBOT_KNOWN_HOSTS" is "{project_root}/tests/gherkin/fixtures/known_hosts"
    Given the environment variable "DEPLOYBOT_DISABLE_ARP" is "1"
    Given the environment variable "DEPLOYBOT_DEPLOY_EXECUTOR" is "{project_root}/tests/gherkin/fixtures/fake_deploy_executor.py"
    Given the environment variable "DEPLOYBOT_FAKE_REMOTE_ROOT" is "{project_root}/tests/gherkin/fixtures/remote_servers"
    Given the environment variable "DEPLOYBOT_PLAIN_PASSWORD_PROMPT" is "1"
    Given the interactive input is "admin\nsecret\n"
    When I run "deploybot services 1"
    Then the command exits with code 0
    And the output contains "Services on localhost (127.0.0.1):"
    And the output contains "1. ngrok: installed"
