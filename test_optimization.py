import time
import json
try:
    import msgpack
except ImportError:
    print("MessagePack not available")
    msgpack = None

# Simple serialization performance test
print('🔍 LOCALHOST OPTIMIZATION - Serialization Performance Test')
print('=' * 60)

# Test data
test_data = {
    'frame_id': 12345,
    'beys': [
        {'id': 0, 'pos_x': 100.0, 'pos_y': 200.0, 'velocity_x': 2.5, 'velocity_y': 1.8},
        {'id': 1, 'pos_x': 150.0, 'pos_y': 230.0, 'velocity_x': -1.2, 'velocity_y': 2.1}
    ],
    'hits': [
        {'pos_x': 125.0, 'pos_y': 215.0, 'is_new_hit': True}
    ]
}

iterations = 1000
print(f'Testing {iterations} iterations...')

# Test JSON serialization
json_times = []
for i in range(iterations):
    start = time.perf_counter()
    result = json.dumps(test_data)
    json_times.append((time.perf_counter() - start) * 1000)

# Test MessagePack serialization if available
msgpack_times = []
if msgpack:
    for i in range(iterations):
        start = time.perf_counter()
        result = msgpack.packb(test_data, use_bin_type=True)
        msgpack_times.append((time.perf_counter() - start) * 1000)

# Test custom string formatting
custom_times = []
for i in range(iterations):
    start = time.perf_counter()
    msg = f"{test_data['frame_id']}, beys:"
    for bey in test_data['beys']:
        msg += f"({bey['id']}, {bey['pos_x']}, {bey['pos_y']})"
    msg += ", hits:"
    for hit in test_data['hits']:
        msg += f"({hit['pos_x']}, {hit['pos_y']})"
    custom_times.append((time.perf_counter() - start) * 1000)

# Calculate averages
json_avg = sum(json_times) / len(json_times)
custom_avg = sum(custom_times) / len(custom_times)

# Test payload sizes
json_size = len(json.dumps(test_data))
custom_result = f"{test_data['frame_id']}, beys:"
for bey in test_data['beys']:
    custom_result += f"({bey['id']}, {bey['pos_x']}, {bey['pos_y']})"
custom_result += ", hits:"
for hit in test_data['hits']:
    custom_result += f"({hit['pos_x']}, {hit['pos_y']})"
custom_size = len(custom_result)

print('')
print('SERIALIZATION PERFORMANCE RESULTS:')
print('-' * 50)
print(f'Method          Avg Time    Payload Size   FPS Limit')
print(f'JSON           {json_avg:8.3f}ms     {json_size:8d}b    {1000/json_avg:8.0f}')
print(f'Custom Format  {custom_avg:8.3f}ms     {custom_size:8d}b    {1000/custom_avg:8.0f}')

if msgpack and msgpack_times:
    msgpack_avg = sum(msgpack_times) / len(msgpack_times)
    msgpack_size = len(msgpack.packb(test_data, use_bin_type=True))
    print(f'MessagePack    {msgpack_avg:8.3f}ms     {msgpack_size:8d}b    {1000/msgpack_avg:8.0f}')

# Frame budget analysis for 60 FPS
frame_budget = 16.67  # ms per frame at 60 FPS
print('')
print('FRAME BUDGET ANALYSIS (60 FPS = 16.67ms per frame):')
print('-' * 50)
print(f'JSON:          {(json_avg/frame_budget)*100:5.1f}% of frame budget')
print(f'Custom Format: {(custom_avg/frame_budget)*100:5.1f}% of frame budget')

if msgpack and msgpack_times:
    print(f'MessagePack:   {(msgpack_avg/frame_budget)*100:5.1f}% of frame budget')

# Test batching performance
print('')
print('📦 EVENT BATCHING PERFORMANCE TEST')
print('=' * 50)

batch_sizes = [1, 3, 5, 10]
batch_results = {}

for batch_size in batch_sizes:
    batch_times = []
    
    for i in range(100):  # 100 iterations per batch size
        # Create batch data
        batch_data = {
            'type': 'batch',
            'count': batch_size,
            'events': [test_data] * batch_size
        }
        
        start = time.perf_counter()
        json.dumps(batch_data)
        batch_time = (time.perf_counter() - start) * 1000
        batch_times.append(batch_time)
    
    avg_batch_time = sum(batch_times) / len(batch_times)
    per_event_time = avg_batch_time / batch_size
    batch_results[batch_size] = {
        'batch_time': avg_batch_time,
        'per_event': per_event_time
    }

print('Batch Size   Batch Time   Per Event    Efficiency')
print('-' * 45)
single_event_time = batch_results[1]['per_event']

for batch_size in batch_sizes:
    batch_time = batch_results[batch_size]['batch_time']
    per_event = batch_results[batch_size]['per_event']
    efficiency = (single_event_time / per_event) * 100
    print(f'{batch_size:8d}   {batch_time:8.3f}ms   {per_event:8.3f}ms   {efficiency:8.1f}%')

# Find optimal batch size
optimal_batch = min(batch_results.keys(), key=lambda bs: batch_results[bs]['per_event'])
optimal_improvement = (single_event_time / batch_results[optimal_batch]['per_event'] - 1) * 100

print('')
print('FINAL RECOMMENDATIONS:')
print('=' * 50)
print(f'1. Use Custom Format for best serialization performance')
print(f'2. Use batch size {optimal_batch} for {optimal_improvement:.1f}% efficiency improvement')
print(f'3. Total CPU usage: <{max((json_avg/frame_budget)*100, (custom_avg/frame_budget)*100):.1f}% of frame budget')

if max((json_avg/frame_budget)*100, (custom_avg/frame_budget)*100) < 10:
    print('✅ Excellent performance for 60 FPS real-time operation')
elif max((json_avg/frame_budget)*100, (custom_avg/frame_budget)*100) < 20:
    print('⚠️  Good performance, monitor under load')
else:
    print('❌ May need optimization for consistent 60 FPS') 