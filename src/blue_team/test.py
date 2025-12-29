from Governor import Governor
from datetime import datetime, timedelta

def test_transactions_analyzer():
    governor = Governor()
    
    # Create a tighter circular transaction pattern with smaller amounts
    # This creates larger distances (1/amount), which should create higher persistence
    base_time = datetime.now()
    
    test_data = [
        # Main circular pattern: A -> B -> C -> A with small amounts (large distances)
        {
            'sender_id': 'user_A',
            'receiver_id': 'user_B',
            'amount': '100000.00',  # Smaller amounts = larger distances
            'timestamp': base_time.strftime("%Y-%m-%d %H:%M:%S")
        },
        {
            'sender_id': 'user_B',
            'receiver_id': 'user_C',
            'amount': '100000000.00',
            'timestamp': (base_time + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        },
        {
            'sender_id': 'user_C',
            'receiver_id': 'user_D',
            'amount': '100000.00',
            'timestamp': (base_time + timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
        },
        {
            'sender_id': 'user_D',
            'receiver_id': 'user_A',
            'amount': '10000.00',
            'timestamp': (base_time + timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
        },
    ]
    
    # Run the analyzer
    result = governor.transactions_analyzer(test_data)
    
    # Print results
    print(f"Found {len(result)} suspicious cases")
    if len(result) > 0:
        for case in result:
            print(f"Type: {case['type']}")
            print(f"Persistence: {case['persistence']:.4f}")
            print(f"Involved users: {case['users']}")
        print("✅ Test detected layering!")
    else:
        print("⚠️ No suspicious cases detected. You may need to adjust the persistence threshold.")
        print("Consider lowering the threshold from 1.0 to something like 0.05 or 0.1")

# Run the test
if __name__ == "__main__":
    test_transactions_analyzer()