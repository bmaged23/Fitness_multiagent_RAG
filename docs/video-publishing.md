# Watching the project demo on GitHub

The README's **Watch demo** link opens the custom HTML video player at:

`https://bmaged23.github.io/Fitness_multiagent_RAG/demo.html`

This streams the existing 4:54 H.264/AAC video in the browser and provides explicit sound and fullscreen controls. The direct MP4 download is a separate README link.

## Enable GitHub Pages

The player and video are in `docs/`. In the repository on GitHub:

1. Open **Settings → Pages**.
2. Under **Build and deployment**, select **Deploy from a branch**.
3. Choose branch **master** and folder **/docs**, then save.
4. Wait for the Pages deployment to finish, then open the player link above.

GitHub Pages can publish the `docs` folder of a branch. This project already has a self-contained player and local relative paths for its video and poster. The README link will work once Pages is enabled and the latest commit is pushed. [GitHub Pages publishing sources](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)

The current MP4 is under GitHub's 10 MB video upload limit for free plans, so it does not need to be reduced for this player. [GitHub supported media formats and limits](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files)
