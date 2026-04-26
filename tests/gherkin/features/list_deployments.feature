Feature: List remote deployments
  DeployBot should list packaged apps already deployed on a discovered remote server, even when those app folders require sudo to enumerate.

  Scenario: List deployments shows numbered remote packages
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
    When I run "deploybot list-deployments 1"
    Then the command exits with code 0
    And the output contains "Deployed apps on localhost (127.0.0.1):"
    And the output contains "1. nested-npm-app-1.2.3 as nested-npm-app: /home/nested-npm-app/ROOT_DEPLOYBOT/nested-npm-app-1.2.3"
