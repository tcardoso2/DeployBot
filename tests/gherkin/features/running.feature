Feature: List running apps
  DeployBot should list the currently running deployed apps on a discovered server.

  Scenario: Running lists a started app with its port
    Given the environment variable "DEPLOYBOT_APP_SEARCH_ROOT" is "{project_root}/tests/gherkin/fixtures/app_search_root"
    Given the environment variable "DEPLOYBOT_DIST_DIR" is "{project_root}/tests/gherkin/fixtures/package_dist"
    Given the environment variable "DEPLOYBOT_KNOWN_HOSTS" is "{project_root}/tests/gherkin/fixtures/known_hosts"
    Given the environment variable "DEPLOYBOT_DISABLE_ARP" is "1"
    Given the environment variable "DEPLOYBOT_DEPLOY_EXECUTOR" is "{project_root}/tests/gherkin/fixtures/fake_deploy_executor.py"
    Given the environment variable "DEPLOYBOT_FAKE_REMOTE_ROOT" is "{project_root}/tests/gherkin/fixtures/remote_servers"
    Given the environment variable "DEPLOYBOT_PLAIN_PASSWORD_PROMPT" is "1"
    Given the path "{project_root}/tests/gherkin/fixtures/package_dist" is removed
    Given the path "{project_root}/tests/gherkin/fixtures/remote_servers" is removed
    When I run "deploybot package 2"
    Then the command exits with code 0
    Given the interactive input is "admin\nsecret\n"
    When I run "deploybot deploy 1 1"
    Then the command exits with code 0
    Given the interactive input is "admin\nsecret\n"
    When I run "deploybot start-app 1 1"
    Then the command exits with code 0
    Given the interactive input is "admin\nsecret\n"
    When I run "deploybot running 1"
    Then the command exits with code 0
    And the output contains "Running apps on localhost (127.0.0.1):"
    And the output contains "1. nested-npm-app-1.2.3 as nested-npm-app on port 41672"
