
# WordPress Migration

This guide is aimed at providing a simple way of migrating your regular WordPress install to Jumpstarter. Given that different hosting environments are quite different we cannot, as of yet, guarantee that the following instructions will work in your case, but it should at least give you some helpful pointers of what needs to be done.

Depending on what type of access you have to your database you may have to find a way to export the database from the [official WordPress guide](https://codex.wordpress.org/Backing_Up_Your_Database) to database backups. Another viable option for exporting/backing up your database is by installing a backup plugin such as [WP-DB-Backup](https://wordpress.org/plugins/wp-db-backup).

Backing up the database is only one part of migrating your WordPress site, you will also need to migrate all the user generated content (files residing in the `wp-content` directory of your site). This can be done in several ways: [Backing Up Your WordPress Files](https://codex.wordpress.org/Backing_Up_Your_WordPress_Files).

_If_ you find anything erroneous in this guide or feel that anything should be clarified further, don't hesitate to either create a pull request or create an issue about it.

## Manual Migration Procedure

The manual procedure assumes that you've got SSH access to the host where you're currently hosting your WordPress site.

_Note_: words written as `<word>` denotes that the word, including `<>` should be replaced by relevant information.

**Tools needed for the migration:**
* SSH (secure shell)
* mysqldump (should be installed on the host where you're currently hosting the site)
* rsync or similar tool for file syncing (scp, ftp)
* sqlite3 (if you don't have this on your local machine you can use the one that Jumpstarter provides)
* a text editor
* awk (again, if you don't have this installed on your local machine you can use the one that Jumpstarter provides)

**Information needed to perform the migration:**
* SSH username for the current host `<cur-ssh-user>`
* SSH host for the current host `<cur-ssh-host>`
* SSH username for your Jumpstarter site `<js-ssh-user>` (this can be found on the site page in the Jumpstarter panel)
* MySQL user name for the current host `<db-user>`
* MySQL password for the current host `<db-password>`
* Remote path to your WordPress installation `<cur-wp-path>`

**Migration steps:**

1. Start a terminal interface.
2. Create a directory for the migration and cd to it. `mkdir WPMigration && cd WPMigration`.
3. Export the remote database: `ssh -C <cur-ssh-user>@<cur-ssh-host> "mysqldump --skip-extended-insert --compact -u<db-user> -p<db-password> <db-name>" > dbdump.sql`
    * If the above command fails with an error saying that it cannot find the command `mysqldump` you need to locate where the `mysqldump` executable is in the file system and then use the full path in the command. You can locate `mysqldump` by issuing `which mysqldump` when logged in on the remote machine.
4. Convert the `dbdump.sql` file to sqlite3 format with the following command using `./mysql2sqlite.sh dbdump.sql | sqlite3 wp-db.sqlite`
    * if you don't have `sqlite3` installed this step can be done in the Jumpstarter environment.
3. Create a directory for the content that is going to be exported from the remote WordPress installation. `mkdir wp`.
4. Download the remote content using `rsync` or similar. `rsync -avz -e 'ssh' <cur-ssh-user>@<cur-ssh-host>:<cur-wp-path>/wp-content wp/`
5. Download the remote `wp-config.php`. `rsync -avz -e 'ssh' <cur-ssh-user>@<cur-ssh-host>:<cur-wp-path>/wp-config.php wp/`
6. Update `wp-config.php` so that it can be used in the Jumpstarter environment
    * Add `define("DB_DIR", "/app/code/wp-db")` before the rest of WordPress is included. A good place is somewhere after the first comment. `*/`
    * Add `/* DO NOT REMOVE: js_config_salts_set: DO NOT REMOVE */` to tell the Jumpstarter plugin that it shouldn't try to set the configuration salts. _Warning_: if this line isn't added to the configuration file your site _will_ become unusable.

    ```php
    <?php
    /**
     * ...
     * @package WordPress
     */

    /* DO NOT REMOVE: js_config_salts_set: DO NOT REMOVE */ // <-- add this line
    define("DB_DIR", "/app/code/wp-db"); // <-- add this line too

    // The following MySQL settings can be cleared as they are no longer needed.

    // ** MySQL settings - You can get this info from your web host ** //
    /** The name of the database for WordPress */
    define('DB_NAME', '');

    /** MySQL database username */
    define('DB_USER', '');
    ```

7. Enable site maintenance mode to deny incoming requests during the migration. (Jumpstarter panel)
8. Sync the created sqlite file to Jumpstarter. `rsync -avz wp-db.sqlite <js-ssh-user>@ssh.jumpstarter.io:/app/code/src/wp-db/.ht.sqlite`
9. Sync the user generated data. `rsync -avz wp/wp-content/* <js-ssh-user>@ssh.jumpstarter.io:/app/code/src/wp-content/`
10. Sync the config file. `rsync -avz wp/wp-config.php <js-ssh-user>@ssh.jumpstarter.io:/app/code/src/`
11. Now it's a good idea to make sure that the migrated site works as intended:
    * SSH into your Jumpstarter site. `ssh <js-ssh-user>@ssh.jumpstarter.io`
    * Execute `/app/code/init`
    * Open a web browser and navigate to the site url. (This can be found on the site page in the Jumpstarter panel)
    * If the site works you can now go back to the terminal and enter `ctrl+c` to stop the init script.
12. Go back to the site in the Jumpstarter panel and disable maintenance mode.
13. Enjoy an old wordpress install in a new environment.
