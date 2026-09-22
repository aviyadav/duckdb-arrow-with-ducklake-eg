MODEL (
  name stage.msdsl.music_info,
  kind FULL,
  description 'Music track metadata and features',
  column_descriptions (
    track_id = 'String track identifier starting with TR',
    name = 'Track title',
    artist = 'Track artist',
    tags = 'Track tags, formatted using title case',
    year = 'Track release year'
  ),
  audits (
    not_null(columns := (
      track_id, name, artist, spotify_preview_url, spotify_id, year, duration_ms,
      danceability, energy, key, loudness, mode, speechiness, acousticness,
      instrumentalness, liveness, valence, tempo, time_signature
    ))
  )
);

SELECT
    track_id,
    name,
    artist,
    spotify_preview_url,
    spotify_id,
    list_transform(
        string_split(tags, ', '),
        tag -> list_aggregate(
            list_transform(
                string_split(tag, '_'),
                tag_word ->
                    ucase(substring(tag_word, 1, 1)) ||
                    lcase(substring(tag_word, 2))
            ),
            'string_agg',
            ' '
        )
    ) AS tags,
    genre,
    year,
    duration_ms,
    danceability,
    energy,
    key,
    loudness,
    mode,
    speechiness,
    acousticness,
    instrumentalness,
    liveness,
    valence,
    tempo,
    time_signature
FROM read_csv(
    @RAW__MILLION_SONG_DATASET_SPOTIFY_LASTFM__MUSIC_INFO,
    delim = ',',
    quote = '"',
    escape = '"',
    header = true,
    columns = {
        track_id: VARCHAR,
        name: VARCHAR,
        artist: VARCHAR,
        spotify_preview_url: VARCHAR,
        spotify_id: VARCHAR,
        tags: VARCHAR,
        genre: VARCHAR,
        year: INTEGER,
        duration_ms: INTEGER,
        danceability: FLOAT,
        energy: FLOAT,
        key: INTEGER,
        loudness: FLOAT,
        mode: INTEGER,
        speechiness: FLOAT,
        acousticness: FLOAT,
        instrumentalness: FLOAT,
        liveness: FLOAT,
        valence: FLOAT,
        tempo: FLOAT,
        time_signature: INTEGER
    }
)
