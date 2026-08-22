import json


def verify_conservation(forecast_file):
    with open(forecast_file) as f:
        data = json.load(f)

    trajectory = data['trajectory']
    t_points = len(trajectory['t'])

    # Conservation check: S+E+IA+IM+IS+H+ICU+R+D = N_pop (roughly)
    # The sum of all states at each time point should be constant

    # N_pop for region-1 is 100,000 (from seed_data.py)
    N_pop = 100000.0

    for i in range(t_points):
        total = (
            trajectory['S'][i] +
            trajectory['E'][i] +
            trajectory['IA'][i] +
            trajectory['IM'][i] +
            trajectory['IS'][i] +
            trajectory['H'][i] +
            trajectory['ICU'][i] +
            trajectory['R'][i] +
            trajectory['D'][i]
        )

        # Checking conservation, allowing for slight floating point error
        if abs(total - N_pop) > 1.0:
            return False, f"Conservation violation at t={trajectory['t'][i]}: sum={total}, expected={N_pop}"

    return True, "Conservation verified."

result, message = verify_conservation('forecast_output.json')
print(f"{result}: {message}")
