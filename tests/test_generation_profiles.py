from authorship_shift.generation_profiles import default_generation_profiles


def test_default_generation_profiles_are_distinct_and_reproducible():
    profiles = default_generation_profiles(base_seed=500)

    assert [profile.name for profile in profiles] == [
        "direct-plain",
        "mechanism-first",
        "constraint-first",
        "evidence-first",
        "compressed-asymmetric",
    ]
    assert len({profile.directive for profile in profiles}) == len(profiles)
    assert [profile.controls.seed for profile in profiles] == [500, 600, 700, 800, 900]


def test_profile_sampling_requests_cover_more_than_one_setting():
    profiles = default_generation_profiles()
    temperatures = {profile.controls.temperature for profile in profiles}
    top_ps = {profile.controls.top_p for profile in profiles}

    assert len(temperatures) > 1
    assert len(top_ps) > 1
