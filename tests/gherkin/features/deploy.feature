Feature: Deploy packaged apps
  DeployBot should deploy a packaged app to a discovered remote server using a dedicated linux user.

  Scenario: Deploy a packaged npm app to a discovered server
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
    And the output contains "Username:"
    And the output contains "Password:"
    And the output contains "Deploying nested-npm-app-1.2.3 to localhost (127.0.0.1)..."
    And the output contains "Deployed as linux user nested-npm-app"
    And the path "{project_root}/tests/gherkin/fixtures/remote_servers/localhost/users/nested-npm-app/ROOT_DEPLOYBOT/nested-npm-app-1.2.3" exists
    And the file "{project_root}/tests/gherkin/fixtures/remote_servers/localhost/users/nested-npm-app/ROOT_DEPLOYBOT/nested-npm-app-1.2.3/INSTALL_LOG.txt" contains "No extra runtime dependencies required"

  Scenario: Deploy a legacy packaged app without a manifest
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
    Given the path "{project_root}/tests/gherkin/fixtures/package_dist/nested-npm-app-1.2.3/deploybot-manifest.json" is removed
    Given the interactive input is "admin\nsecret\n"
    When I run "deploybot deploy 1 1"
    Then the command exits with code 0
    And the output contains "Username:"
    And the output contains "Password:"
    And the file "{project_root}/tests/gherkin/fixtures/package_dist/nested-npm-app-1.2.3/deploybot-manifest.json" contains "package_version"
