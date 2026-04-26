Feature: List deployable apps
  DeployBot should find deployable apps one level above the workspace and one folder below each of those folders, including npm apps.

  Scenario: List apps includes a sibling app and a nested npm app
    Given the environment variable "DEPLOYBOT_APP_SEARCH_ROOT" is "{project_root}/tests/gherkin/fixtures/app_search_root"
    When I run "deploybot list-apps"
    Then the command exits with code 0
    And the output contains "Detected deployable apps:"
    And the output contains "1. sibling-python-app: {project_root}/tests/gherkin/fixtures/app_search_root/sibling-python-app"
    And the output contains "2. nested-npm-app: {project_root}/tests/gherkin/fixtures/app_search_root/tools/nested-npm-app"
