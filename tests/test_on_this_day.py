import datetime
import os

from tiklocal.app import create_app


def make_client(tmp_path, dated_files):
    media_root = tmp_path / 'media'
    media_root.mkdir()
    for name, moment in dated_files.items():
        path = media_root / name
        path.write_bytes(b'media')
        stamp = moment.timestamp()
        os.utime(path, (stamp, stamp))
    return create_app({'TESTING': True, 'MEDIA_ROOT': media_root}).test_client()


def on_this_day(client, date):
    return client.get(f'/api/library/on-this-day?date={date}').get_json()['data']


def test_groups_past_years_on_the_same_day(tmp_path):
    client = make_client(tmp_path, {
        'a.jpg': datetime.datetime(2023, 9, 28, 10),
        'b.mp4': datetime.datetime(2023, 9, 28, 18),
        'c.jpg': datetime.datetime(2021, 9, 28, 9),
        'this-year.jpg': datetime.datetime(2026, 9, 28, 9),
        'other-day.jpg': datetime.datetime(2023, 9, 26, 9),
    })
    data = on_this_day(client, '2026-09-28')
    assert data['window'] == 'day'
    assert [(group['year'], group['years_ago'], [item['name'] for item in group['items']]) for group in data['years']] == [
        (2023, 3, ['@default/b.mp4', '@default/a.jpg']),
        (2021, 5, ['@default/c.jpg']),
    ]


def test_widens_to_the_week_and_stays_empty_without_matches(tmp_path):
    client = make_client(tmp_path, {'near.jpg': datetime.datetime(2024, 9, 30, 9)})
    data = on_this_day(client, '2026-09-28')
    assert data['window'] == 'week'
    assert [group['year'] for group in data['years']] == [2024]
    assert on_this_day(client, '2026-03-01')['years'] == []
