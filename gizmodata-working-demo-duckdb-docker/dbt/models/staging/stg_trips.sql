select
    ride_id,
    rideable_type,
    member_casual,
    start_station_name,
    end_station_name,
    started_at,
    ended_at,
    date_diff('second', started_at, ended_at) / 60.0 as ride_minutes
from {{ source('divvy_raw', 'trips') }}
where ended_at > started_at
-- The published Divvy extracts contain a few ride_ids that appear twice
-- (the same trip re-published across monthly files); keep one row per ride.
qualify row_number() over (partition by ride_id order by started_at) = 1
