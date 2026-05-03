Feature: Terminal UI
  DeployBot should expose the same workflows through a terminal UI entrypoint.

  Scenario: The TUI can run the same deploy workflow in plain scripted mode
    Given the environment variable "DEPLOYBOT_APP_SEARCH_ROOT" is "{project_root}/tests/gherkin/fixtures/app_search_root"
    Given the environment variable "DEPLOYBOT_DIST_DIR" is "{project_root}/tests/gherkin/fixtures/package_dist"
    Given the environment variable "DEPLOYBOT_KNOWN_HOSTS" is "{project_root}/tests/gherkin/fixtures/known_hosts"
    Given the environment variable "DEPLOYBOT_DISABLE_ARP" is "1"
    Given the environment variable "DEPLOYBOT_DEPLOY_EXECUTOR" is "{project_root}/tests/gherkin/fixtures/fake_deploy_executor.py"
    Given the environment variable "DEPLOYBOT_REMOTE_EXECUTOR" is "{project_root}/tests/gherkin/fixtures/fake_remote_executor.py"
    Given the environment variable "DEPLOYBOT_FAKE_REMOTE_ROOT" is "{project_root}/tests/gherkin/fixtures/remote_servers"
    Given the environment variable "DEPLOYBOT_PLAIN_PASSWORD_PROMPT" is "1"
    Given the path "{project_root}/tests/gherkin/fixtures/package_dist" is removed
    Given the path "{project_root}/tests/gherkin/fixtures/remote_servers" is removed
    Given the interactive input is "list-apps\npackage\n2\nlist-packages\ndiscover\nn\n32\ndeploy\n1\n1\nadmin\nsecret\nlist-deployments\n1\nadmin\nsecret\nstart-app-custom\n1\n1\npython3 -m http.server 43000 --bind 0.0.0.0\nadmin\nsecret\nstart-app\n1\n1\nadmin\nsecret\nrunning\n1\nadmin\nsecret\nservices\n1\nadmin\nsecret\nstart-tunnel\n1\n1\ndemo-space\nadmin\nsecret\nstop-tunnel\n1\n1\ndemo-space\nadmin\nsecret\nstop-app\n1\n1\nadmin\nsecret\nremote\n1\nhostname\ntester\nsecret\nq\n"
    When I run "deploybot-tui"
    Then the command exits with code 0
    And the output contains "DeployBot TUI"
    And the output contains "Detected deployable apps:"
    And the output contains "Packaged nested-npm-app as nested-npm-app-1.2.3"
    And the output contains "Packaged apps:"
    And the output contains "Discovered devices:"
    And the output contains "Deployed as linux user nested-npm-app"
    And the output contains "Deployed apps on localhost (127.0.0.1):"
    And the output contains "Started custom command as nested-npm-app"
    And the output contains "Started app as nested-npm-app on port 41672"
    And the output contains "Running apps on localhost (127.0.0.1):"
    And the output contains "Services on localhost (127.0.0.1):"
    And the output contains "Started tunnel at https://demo-space.ngrok.app"
    And the output contains "Stopped tunnel for nested-npm-app-1.2.3 on demo-space"
    And the output contains "Stopped nested-npm-app-1.2.3 as nested-npm-app"
    And the output contains "mock-hostname-for-localhost"
    And the path "{project_root}/tests/gherkin/fixtures/remote_servers/localhost/users/nested-npm-app/ROOT_DEPLOYBOT/nested-npm-app-1.2.3" exists
