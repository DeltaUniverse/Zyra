"""Makes the Zyra bot package executable.

This allows the bot to be run directly using `python -m zyra`, which will
invoke the `main()` function from the `main` module.
"""

import main

if __name__ == "__main__":
    main.main()
