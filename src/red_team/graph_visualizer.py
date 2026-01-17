"""
Transaction Graph Visualizer for Fraud Simulation
==================================================
Place this file in src/red_team/graph_visualizer.py

Simple graph with colored fraud/banned nodes and statistics.
"""

import os
import json
import networkx as nx
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

# Import project config
try:
    from src.common.config import Config
except ImportError:
    try:
        from common.config import Config
    except ImportError:
        class Config:
            REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
            REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
            KEY_BANNED = "sim:banned"
            KEY_IDENTITY = "sim:identity"

# Redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Plotly (required for HTML)
try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    print("⚠️  Plotly not installed. Run: pip install plotly")


class TransactionGraphVisualizer:
    """Visualizes transaction network from Redis as interactive HTML."""
    
    NODE_COLORS = {
        'student': '#3498db',
        'worker': '#2ecc71',
        'entrepreneur': '#9b59b6',
        'bot': '#e74c3c',
        'fraud_dirty': '#c0392b',
        'fraud_clean': '#e67e22',
        'fraudster': '#e74c3c',
        'civilian': '#3498db',
        'unknown': '#95a5a6',
        'banned': '#2c3e50',
    }
    
    EDGE_COLORS = {
        'CIVIL': '#bdc3c7',
        'FRAUD': '#e74c3c',
    }
    
    def __init__(self):
        self.redis_client = None
        self.G = nx.DiGraph()
        self.banned_nodes = set()
        self.node_types = {}
        self.stats = defaultdict(float)
    
    def connect_redis(self):
        """Connect to Redis."""
        if not REDIS_AVAILABLE:
            return False
        try:
            self.redis_client = redis.Redis(
                host=Config.REDIS_HOST,
                port=Config.REDIS_PORT,
                db=0,
                decode_responses=True
            )
            self.redis_client.ping()
            return True
        except:
            return False
    
    def load_from_stream(self, stream_name='money_flow', max_count=50000):
        """Load transactions from Redis stream."""
        if not self.redis_client:
            if not self.connect_redis():
                return False
        
        try:
            entries = self.redis_client.xrange(stream_name, count=max_count)
            if not entries:
                return False
            
            for entry_id, data in entries:
                sender = data.get('sender_id', 'unknown')
                receiver = data.get('receiver_id', 'unknown')
                amount = float(data.get('amount', 0))
                tx_type = data.get('type', 'CIVIL')
                
                if sender not in self.G:
                    self.G.add_node(sender)
                if receiver not in self.G:
                    self.G.add_node(receiver)
                
                if self.G.has_edge(sender, receiver):
                    self.G[sender][receiver]['weight'] += amount
                    self.G[sender][receiver]['count'] += 1
                else:
                    self.G.add_edge(sender, receiver, weight=amount, count=1, tx_type=tx_type)
                
                self.stats['total_transactions'] += 1
                self.stats['total_volume'] += amount
                if tx_type == 'FRAUD':
                    self.stats['fraud_transactions'] += 1
                    self.stats['fraud_volume'] += amount
            
            return True
        except Exception as e:
            print(f"Error loading stream: {e}")
            return False
    
    def load_identity_map(self):
        """Placeholder for compatibility."""
        pass
    
    def load_banned_nodes(self):
        """Load banned users."""
        if not self.redis_client:
            return
        try:
            self.banned_nodes = self.redis_client.smembers(Config.KEY_BANNED)
        except:
            pass
    
    def load_fraud_alerts(self, channel='governor:alerts'):
        """Placeholder for compatibility."""
        pass
    
    def assign_node_types(self):
        """Assign node types based on transaction patterns."""
        for node in self.G.nodes():
            # Check if banned first
            if node in self.banned_nodes:
                self.node_types[node] = 'banned'
                continue
            
            # Check fraud involvement
            fraud_edges = sum(1 for _, _, d in self.G.in_edges(node, data=True) 
                             if d.get('tx_type') == 'FRAUD')
            fraud_edges += sum(1 for _, _, d in self.G.out_edges(node, data=True) 
                              if d.get('tx_type') == 'FRAUD')
            
            if fraud_edges > 0:
                out_deg = self.G.out_degree(node)
                in_deg = self.G.in_degree(node)
                if out_deg > in_deg * 3:
                    self.node_types[node] = 'fraud_dirty'
                elif in_deg > out_deg * 3:
                    self.node_types[node] = 'fraud_clean'
                else:
                    self.node_types[node] = 'bot'
            else:
                self.node_types[node] = 'civilian'
    
    def visualize_html(self, output_path='transaction_graph.html', turn_number=None):
        """Create interactive HTML visualization with statistics."""
        if not PLOTLY_AVAILABLE:
            print("Plotly not installed - skipping HTML")
            return None
        
        if self.G.number_of_nodes() == 0:
            return None
        
        # Assign node types for coloring
        self.assign_node_types()
        
        pos = nx.spring_layout(self.G, k=2, iterations=50, seed=42)
        
        # Edges - colored by type
        civil_edge_x, civil_edge_y = [], []
        fraud_edge_x, fraud_edge_y = [], []
        
        for u, v, data in self.G.edges(data=True):
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            if data.get('tx_type') == 'FRAUD':
                fraud_edge_x.extend([x0, x1, None])
                fraud_edge_y.extend([y0, y1, None])
            else:
                civil_edge_x.extend([x0, x1, None])
                civil_edge_y.extend([y0, y1, None])
        
        # Civil edges trace
        civil_edge_trace = go.Scatter(
            x=civil_edge_x, y=civil_edge_y,
            mode='lines',
            line=dict(width=1, color=self.EDGE_COLORS['CIVIL']),
            hoverinfo='none',
            opacity=0.5
        )
        
        # Fraud edges trace
        fraud_edge_trace = go.Scatter(
            x=fraud_edge_x, y=fraud_edge_y,
            mode='lines',
            line=dict(width=1, color=self.EDGE_COLORS['FRAUD']),
            hoverinfo='none',
            opacity=0.7
        )
        
        # Nodes - colored by type
        node_x = [pos[n][0] for n in self.G.nodes()]
        node_y = [pos[n][1] for n in self.G.nodes()]
        node_colors = [self.NODE_COLORS.get(self.node_types.get(n, 'civilian'), '#3498db') 
                       for n in self.G.nodes()]
        
        # Hover text
        node_text = []
        for n in self.G.nodes():
            vol = sum(d['weight'] for _, _, d in self.G.in_edges(n, data=True))
            vol += sum(d['weight'] for _, _, d in self.G.out_edges(n, data=True))
            node_type = self.node_types.get(n, 'civilian')
            status = "🚫 BANNED" if n in self.banned_nodes else ""
            node_text.append(
                f"<b>ID:</b> {n}<br>"
                f"<b>Type:</b> {node_type}<br>"
                f"<b>Volume:</b> ${vol:,.0f}<br>"
                f"{status}"
            )
        
        node_trace = go.Scatter(
            x=node_x, y=node_y,
            mode='markers',
            hoverinfo='text',
            text=node_text,
            marker=dict(
                color=node_colors,
                size=15,
                line=dict(width=1, color='white')
            )
        )
        
        # Calculate statistics
        fraud_pct = (self.stats['fraud_transactions'] / max(self.stats['total_transactions'], 1) * 100)
        
        # Build title
        if turn_number:
            title_text = f'Transaction Network - Turn {turn_number}'
        else:
            title_text = 'Transaction Network - Final'
        
        # Create figure
        fig = go.Figure(
            data=[civil_edge_trace, fraud_edge_trace, node_trace],
            layout=go.Layout(
                title=dict(
                    text=title_text,
                    font=dict(size=20)
                ),
                showlegend=False,
                hovermode='closest',
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                plot_bgcolor='white',
                paper_bgcolor='white',
                
                # Add statistics as annotations
                annotations=[
                    # Stats box (top-left)
                    dict(
                        text=(
                            f"<b>📊 Statistics</b><br>"
                            f"Nodes: {self.G.number_of_nodes()}<br>"
                            f"Edges: {self.G.number_of_edges()}<br>"
                            f"Total Txs: {int(self.stats['total_transactions']):,}<br>"
                            f"Total Volume: ${self.stats['total_volume']:,.0f}<br>"
                            f"<br>"
                            f"<b>🎭 Fraud Activity</b><br>"
                            f"Fraud Txs: {int(self.stats['fraud_transactions']):,} ({fraud_pct:.1f}%)<br>"
                            f"Fraud Volume: ${self.stats['fraud_volume']:,.0f}<br>"
                            f"<br>"
                            f"<b>🚫 Banned: {len(self.banned_nodes)}</b>"
                        ),
                        showarrow=False,
                        xref="paper", yref="paper",
                        x=0.01, y=0.99,
                        xanchor='left', yanchor='top',
                        font=dict(size=11),
                        bgcolor="rgba(255,255,255,0.9)",
                        bordercolor="gray",
                        borderwidth=1,
                        borderpad=10,
                        align='left'
                    )
                ]
            )
        )
        
        fig.write_html(output_path)
        print(f"💾 Saved: {output_path}")
        return fig