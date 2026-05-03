Feature: CLI help
  DeployBot should describe its available features from the command line.

  Scenario: Requesting help lists the supported features
    When I run "deploybot -help"
    Then the command exits with code 0
    And the output contains "Features:"
    And the output contains "discover: detect devices on the local network"
    And the output contains "list-apps: find deployable apps in sibling folders"
    And the output contains "package: build and package a discovered app into DeployBot/dist"
    And the output contains "list-packages: list the versioned packages available in DeployBot/dist"
    And the output contains "deploy: deploy a packaged app to a discovered server"
    And the output contains "list-deployments: list packaged apps already deployed on a discovered server"
    And the output contains "start-app: start a deployed app on a discovered server and report its runtime port"
    And the output contains "startup-points: inspect the commands start-app will run"
    And the output contains "stop-app: stop a deployed app on a discovered server"
    And the output contains "running: list currently running apps on a discovered server"
    And the output contains "services: list detectable remote services on a discovered server"
    And the output contains "start-tunnel: start an ngrok tunnel for a deployed app and print its public URL"
    And the output contains "stop-tunnel: stop an ngrok tunnel for a deployed app and subdomain"
    And the output contains "remote: select a discovered host number and run a remote command"
