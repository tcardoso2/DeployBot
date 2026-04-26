Feature: List built packages
  DeployBot should show numbered packages from the dist folder.

  Scenario: List packages shows versioned outputs
    Given the environment variable "DEPLOYBOT_APP_SEARCH_ROOT" is "{project_root}/tests/gherkin/fixtures/app_search_root"
    Given the environment variable "DEPLOYBOT_DIST_DIR" is "{project_root}/tests/gherkin/fixtures/package_dist"
    Given the path "{project_root}/tests/gherkin/fixtures/package_dist" is removed
    When I run "deploybot package 2"
    Then the command exits with code 0
    When I run "deploybot package 2"
    Then the command exits with code 0
    When I run "deploybot list-packages"
    Then the command exits with code 0
    And the output contains "Packaged apps:"
    And the output contains "1. nested-npm-app-1.2.3: {project_root}/tests/gherkin/fixtures/package_dist/nested-npm-app-1.2.3"
    And the output contains "2. nested-npm-app-1.2.4: {project_root}/tests/gherkin/fixtures/package_dist/nested-npm-app-1.2.4"
