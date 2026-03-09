# Upgraderr

## Intro

After the whole `Huntarr` fallout, I realized I missed the functionality of a service like it that would constantly search for and upgrade my media in `Sonarr` and `Radarr`. There are scripts like [upgradinatorr](https://github.com/angrycuban13/Just-A-Bunch-Of-Starr-Scripts/blob/main/Upgradinatorr/README.md) that exists but I wanted something not written in powershell :lol: so I could understand it that and had a really easy docker setup. It did take some time to get a full grasp of how it works and to find where I felt improvements could be made, and so with that I wrote this little service up! I definitely avoided using any AI tooling when writing up this project so forgive me for any horrendous code you find.

## How does it work ?

By just defining your `Arr` apps `Upgraderr` will synchronize your media state to it's database and attempt to trigger indexer searches based on the following decision tree:

```mermaid
graph TD;
    A[Movie/Episode] --> B{Is Monitored?}
    B -- Yes --> C{Is Missing?}
    B -- No --> D[Skip]
    C -- Yes --> E[Trigger Search]
    C -- No --> F{Is Custom Format Score Exceeded Cutoff?}
    F -- Yes --> G[Skip]
    F -- No --> H[Trigger Search]
```

## Why do I even need this?

I noticed a lot of people never really understood the want for this kind of application and to be fair it is catered to a really specific want that the `Arr` apps don't fulfill. `Arr` apps perform full indexer searches when clicking on a button from their UI or from applications like `Seerr` when requesting media. But once an Episode or Season from a Series is added, after the initial search, the `Arr` apps rely purely on RSS Feeds for searching. So if you ever join a new tracker or if you missed a release due to rate-limiting from an indexer, there's a good chance you missed a high quality media file. This script aims to solve that by periodically triggering full searches for your media items.

## Configuration

These are the different environment variables that can be configured:

| Variable                  | Description                                                                                                                                                                                    |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SONARR_URL`              | The URL of your Sonarr instance                                                                                                                                                                |
| `SONARR_API_KEY`          | The API key for your Sonarr instance                                                                                                                                                           |
| `RADARR_URL`              | The URL of your Radarr instance                                                                                                                                                                |
| `RADARR_API_KEY`          | The API key for your Radarr instance                                                                                                                                                           |
| `DRY_RUN`                 | If set to `true ` the script will not trigger any searches                                                                                                                                     |
| `LOG_LEVEL`               | The log level for the script                                                                                                                                                                   |
| `LOGS_DIRECTORY`          | The directory where the logs are stored                                                                                                                                                        |
| `MAX_SEARCH_LIMIT`        | The maximum number of searches that can be triggered in a single run                                                                                                                           |
| `NOTIFICATION_URL`        | An Apprise URL for notifications                                                                                                                                                               |
| `ONE_SHOT`                | If set to `true` the script will run once and then exit                                                                                                                                        |
| `SEARCH_INTERVAL`         | The interval (in minutes) between searches                                                                                                                                                     |
| `SEARCH_REFRESH_INTERVAL` | The interval (in minutes) after which a media item will be searched again                                                                                                                      |
| `SONARR_SEARCH`           | The type of search that will be performed for a season. `command` is the same as clicking on search in sonarr. `release` attempts to run an interactive search and picks the best season pack. |

## Notifications

`Upgraderr` uses [apprise](https://appriseit.com/services/) for notification handling, so any service that is supported there is supported in this application!
