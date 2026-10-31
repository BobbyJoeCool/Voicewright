# Sound effects resolve from a local sound library, not live Freesound search

The original plan called the Freesound API at generation time. We decided instead that every `{name}` in a script resolves to a file in a local sound library. The user fills the library by searching Freesound in the app, picking a result, and downloading it with its license. Reasons: the app's goal is to run locally, generation should give the same sound every run, and each sound's license should be reviewed when it's picked, not discovered after an output is shared.

## Considered Options

- **Live Freesound search at generation time:** least effort per script, but it needs internet and an API key for every run, returns different sounds each run, and uses sounds whose licenses nobody reviewed.
- **Local library with no Freesound integration:** simplest, but the user has to find, download, and convert every sound by hand.

## Consequences

- A script that names a sound missing from the library is rejected before generation, with a link to the Freesound picker for each missing name.
- License and attribution are stored per sound, which is what lets saved output records list sound credits.
- Generated sound effects (Stable Audio Open, a future version) go into the same library.
