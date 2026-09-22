MODEL (
  name stage.msdsl.user_listening_history,
  kind FULL,
  description 'User listening history with play count per track',
  column_descriptions (
    track_id = 'String track identifier starting with TR',
    user_id = 'User ID for Million Song Dataset, Spotify, and Last.fm (MSDSL)',
    play_count = 'Number of times the user played the track'
  ),
  audits (
    not_null(columns := (track_id, user_id)),
    positive_integer(column := play_count)
  )
);

SELECT
    track_id,
    user_id,
    playcount AS play_count
FROM read_csv(
    @RAW__MILLION_SONG_DATASET_SPOTIFY_LASTFM__USER_LISTENING_HISTORY,
    delim = ',',
    header = true,
    columns = {
        track_id: VARCHAR,
        user_id: VARCHAR,
        playcount: INTEGER
    }
)
