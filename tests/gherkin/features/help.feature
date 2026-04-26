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
    And the output contains "deploy: copy a selected sibling app to a discovered device"
    And the output contains "remote: select a discovered host number and run a remote command"
