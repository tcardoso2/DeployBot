Feature: Manage remote tunnels
  DeployBot should start and stop ngrok tunnels for running deployed apps on a discovered server.

  Scenario: Start and stop a tunnel for a running app
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
    When I run "deploybot start-tunnel 1 1 demo-space"
    Then the command exits with code 0
    And the output contains "Starting tunnel for nested-npm-app-1.2.3 on localhost (127.0.0.1)..."
    And the output contains "Started tunnel at https://demo-space.ngrok.app"
    And the path "{project_root}/tests/gherkin/fixtures/remote_servers/localhost/users/nested-npm-app/ROOT_DEPLOYBOT/.deploybot-tunnels/nested-npm-app-1.2.3-demo-space.json" exists
    Given the interactive input is "admin\nsecret\n"
    When I run "deploybot stop-tunnel 1 1 demo-space"
    Then the command exits with code 0
    And the output contains "Stopping tunnel for nested-npm-app-1.2.3 on localhost (127.0.0.1)..."
    And the output contains "Stopped tunnel for nested-npm-app-1.2.3 on demo-space"
