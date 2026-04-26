Feature: Package deployable apps
  DeployBot should build a listed app and store versioned output folders in dist.

  Scenario: Package a nested npm app twice with incrementing versions
    Given the environment variable "DEPLOYBOT_APP_SEARCH_ROOT" is "{project_root}/tests/gherkin/fixtures/app_search_root"
    Given the environment variable "DEPLOYBOT_DIST_DIR" is "{project_root}/tests/gherkin/fixtures/package_dist"
    Given the path "{project_root}/tests/gherkin/fixtures/package_dist" is removed
    When I run "deploybot package 2"
    Then the command exits with code 0
    And the output contains "Packaged nested-npm-app as nested-npm-app-1.2.3"
    And the path "{project_root}/tests/gherkin/fixtures/package_dist/nested-npm-app-1.2.3" exists
    And the file "{project_root}/tests/gherkin/fixtures/package_dist/nested-npm-app-1.2.3/index.html" contains "Nested NPM App"
    And the file "{project_root}/tests/gherkin/fixtures/package_dist/nested-npm-app-1.2.3/deploybot-manifest.json" contains "package_version"
    When I run "deploybot package 2"
    Then the command exits with code 0
    And the output contains "Packaged nested-npm-app as nested-npm-app-1.2.4"
    And the path "{project_root}/tests/gherkin/fixtures/package_dist/nested-npm-app-1.2.4" exists
