Feature: Remote command execution
  DeployBot should let me choose a discovered host by number and run a remote command after prompting for credentials.

  Scenario: Execute hostname against a numbered known host
    Given the environment variable "DEPLOYBOT_KNOWN_HOSTS" is "{project_root}/tests/gherkin/fixtures/known_hosts"
    Given the environment variable "DEPLOYBOT_DISABLE_ARP" is "1"
    Given the environment variable "DEPLOYBOT_REMOTE_EXECUTOR" is "{project_root}/tests/gherkin/fixtures/fake_remote_executor.py"
    Given the environment variable "DEPLOYBOT_PLAIN_PASSWORD_PROMPT" is "1"
    Given the interactive input is "tester\nsecret\n"
    When I run "deploybot remote 1 hostname"
    Then the command exits with code 0
    And the output contains "Username:"
    And the output contains "Password:"
    And the output contains "Connecting to localhost (127.0.0.1)..."
    And the output contains "mock-hostname-for-localhost"
