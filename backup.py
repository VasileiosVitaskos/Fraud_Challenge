"""
Transaction Graph Visualizer for Fraud Simulation
==================================================
Visualizes the transaction network from Redis stream data.

Place this file in your project root (same level as audit.py)

Usage:
    python graph_visualizer.py                    # Display on screen
    python graph_visualizer.py --output png       # Save as PNG
    python graph_visualizer.py --output html      # Interactive HTML
"""

import os
import sys
import json
import argparse
import numpy as np
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

# Import project config
try:
    from src.common.config import Config
except ImportError:
    # Fallback if running from different directory
    class Config:
        REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
        REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
        KEY_TRANSACTIONS = "sim:transactions"
        KEY_BALANCES = "sim:balances"
        KEY_BANNED = "sim:banned"
        KEY_GAME_STATE = "sim:state"
        KEY_IDENTITY = "sim:identity"
        TOTAL_TICKS = 200

# Redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("⚠️  Redis not installed. Run: pip install redis")

# Plotly (optional)
try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


class TransactionGraphVisualizer:
    """Visualizes transaction network from Redis."""
    
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
        """Initialize using project Config."""
        self.redis_client = None
        self.G = nx.DiGraph()
        self.node_types = {}
        self.banned_nodes = set()
        self.identity_map = {}
        
        self.detected_cycles = []
        self.detected_triangles = []
        self.smurfing_hubs = []
        
        self.stats = defaultdict(float)
    
    def connect_redis(self):
        """Connect to Redis using project Config."""
        if not REDIS_AVAILABLE:
            print("❌ Redis library not installed!")
            return False
        
        try:
            self.redis_client = redis.Redis(
                host=Config.REDIS_HOST,
                port=Config.REDIS_PORT,
                db=0,
                decode_responses=True
            )
            self.redis_client.ping()
            print(f"✅ Connected to Redis at {Config.REDIS_HOST}:{Config.REDIS_PORT}")
            return True
        except redis.ConnectionError as e:
            print(f"❌ Redis connection failed: {e}")
            return False
    
    def load_identity_map(self):
        """Load user identities from KEY_IDENTITY (sim:identity)."""
        if not self.redis_client:
            return
        
        try:
            identity_data = self.redis_client.hgetall(Config.KEY_IDENTITY)
            self.identity_map = {k: v.lower() for k, v in identity_data.items()}
            print(f"👤 Loaded {len(self.identity_map)} user identities")
        except Exception as e:
            print(f"⚠️  Could not load identities: {e}")
    
    def load_banned_nodes(self):
        """Load banned users from KEY_BANNED (sim:banned)."""
        if not self.redis_client:
            return
        
        try:
            self.banned_nodes = self.redis_client.smembers(Config.KEY_BANNED)
            if self.banned_nodes:
                print(f"🚫 Loaded {len(self.banned_nodes)} banned nodes")
        except Exception as e:
            print(f"⚠️  Could not load banned nodes: {e}")
    
    def load_from_stream(self, stream_name='money_flow', max_count=50000):
        """Load transactions from Redis stream."""
        if not self.redis_client:
            if not self.connect_redis():
                return False
        
        try:
            entries = self.redis_client.xrange(stream_name, count=max_count)
            
            if not entries:
                print(f"⚠️  No transactions in stream '{stream_name}'")
                return False
            
            print(f"📊 Loading {len(entries)} transactions...")
            
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
            
            print(f"✅ Loaded: {self.G.number_of_nodes()} nodes, {self.G.number_of_edges()} edges")
            return True
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def load_fraud_alerts(self, channel='governor:alerts'):
        """Load fraud alerts from Governor."""
        if not self.redis_client:
            return
        
        try:
            alerts = self.redis_client.lrange(channel, 0, -1)
            
            for alert_json in alerts:
                try:
                    alert = json.loads(alert_json)
                    alert_type = alert.get('type', '')
                    details = alert.get('details', [])
                    
                    if alert_type == 'Layering':
                        for case in details:
                            users = case.get('users', [])
                            if users:
                                self.detected_cycles.append(users)
                    
                    elif alert_type == 'Smurfing':
                        for case_group in details:
                            cases = case_group.get('cases', [])
                            for case in cases:
                                hub = case.get('hub')
                                if hub:
                                    self.smurfing_hubs.append(hub)
                    
                    elif alert_type == 'Structuring':
                        for case in details:
                            users = case.get('users', [])
                            if users:
                                self.detected_triangles.append(users)
                except:
                    continue
            
            if self.detected_cycles or self.smurfing_hubs or self.detected_triangles:
                print(f"🔍 Fraud alerts: {len(self.detected_cycles)} cycles, "
                      f"{len(set(self.smurfing_hubs))} hubs, {len(self.detected_triangles)} triangles")
        except:
            pass
    
    def assign_node_types(self):
        """Assign node types using identity map or inference."""
        for node in self.G.nodes():
            if node in self.banned_nodes:
                self.node_types[node] = 'banned'
                continue
            
            if node in self.identity_map:
                identity = self.identity_map[node]
                if 'fraud' in identity or 'bot' in identity:
                    self.node_types[node] = 'fraudster'
                else:
                    self.node_types[node] = 'civilian'
                continue
            
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
                vol = sum(d['weight'] for _, _, d in self.G.out_edges(node, data=True))
                if vol > 5000:
                    self.node_types[node] = 'entrepreneur'
                elif vol > 1000:
                    self.node_types[node] = 'worker'
                else:
                    self.node_types[node] = 'student'
    
    def get_node_colors(self):
        return [self.NODE_COLORS.get(self.node_types.get(n, 'unknown'), '#95a5a6') 
                for n in self.G.nodes()]
    
    def get_edge_colors(self):
        return [self.EDGE_COLORS.get(d.get('tx_type', 'CIVIL'), '#bdc3c7') 
                for _, _, d in self.G.edges(data=True)]
    
    def get_edge_widths(self, min_w=0.5, max_w=5.0):
        weights = [d['weight'] for _, _, d in self.G.edges(data=True)]
        if not weights or max(weights) == min(weights):
            return [2.0] * len(weights)
        min_wt, max_wt = min(weights), max(weights)
        return [min_w + (w - min_wt) / (max_wt - min_wt) * (max_w - min_w) for w in weights]
    
    def get_node_sizes(self, min_s=100, max_s=1000):
        volumes = {}
        for node in self.G.nodes():
            vol = sum(d['weight'] for _, _, d in self.G.in_edges(node, data=True))
            vol += sum(d['weight'] for _, _, d in self.G.out_edges(node, data=True))
            volumes[node] = vol
        
        if not volumes or max(volumes.values()) == min(volumes.values()):
            return [300] * self.G.number_of_nodes()
        
        min_v, max_v = min(volumes.values()), max(volumes.values())
        return [min_s + (volumes[n] - min_v) / (max_v - min_v) * (max_s - min_s) 
                for n in self.G.nodes()]
    
    def visualize(self, layout='spring', figsize=(16, 12), show_labels=True,
                  highlight_fraud=True, save_path=None):
        """Create matplotlib visualization."""
        
        if self.G.number_of_nodes() == 0:
            print("❌ No data to visualize!")
            return None
        
        if not self.node_types:
            self.assign_node_types()
        
        fig, ax = plt.subplots(figsize=figsize)
        ax.set_title("Transaction Network Graph", fontsize=16, fontweight='bold')
        
        print(f"📐 Computing {layout} layout...")
        layouts = {
            'spring': lambda: nx.spring_layout(self.G, k=2, iterations=50, seed=42),
            'kamada_kawai': lambda: nx.kamada_kawai_layout(self.G),
            'circular': lambda: nx.circular_layout(self.G),
        }
        pos = layouts.get(layout, layouts['spring'])()
        
        nx.draw_networkx_edges(self.G, pos, ax=ax, edge_color=self.get_edge_colors(),
                               width=self.get_edge_widths(), alpha=0.6, arrows=True,
                               arrowsize=10, connectionstyle='arc3,rad=0.1')
        
        node_sizes = self.get_node_sizes()
        nx.draw_networkx_nodes(self.G, pos, ax=ax, node_color=self.get_node_colors(),
                               node_size=node_sizes, alpha=0.9, edgecolors='white', linewidths=1.5)
        
        if show_labels and self.G.number_of_nodes() <= 50:
            labels = {n: n[:4] + '..' for n in self.G.nodes()}
            nx.draw_networkx_labels(self.G, pos, ax=ax, labels=labels,
                                   font_size=7, font_color='white', font_weight='bold')
        
        if highlight_fraud:
            nodes_list = list(self.G.nodes())
            
            for cycle_users in self.detected_cycles:
                cycle_nodes = [n for n in cycle_users if n in self.G]
                if len(cycle_nodes) >= 2:
                    sizes = [node_sizes[nodes_list.index(n)] * 1.5 for n in cycle_nodes]
                    nx.draw_networkx_nodes(self.G, pos, ax=ax, nodelist=cycle_nodes,
                                          node_color='none', edgecolors='#f39c12',
                                          linewidths=4, node_size=sizes)
            
            for hub in set(self.smurfing_hubs):
                if hub in self.G:
                    idx = nodes_list.index(hub)
                    nx.draw_networkx_nodes(self.G, pos, ax=ax, nodelist=[hub],
                                          node_color='none', edgecolors='#e74c3c',
                                          linewidths=5, node_size=[node_sizes[idx] * 2],
                                          node_shape='s')
        
        legend_items = ['student', 'worker', 'entrepreneur', 'bot', 'fraud_dirty', 'fraud_clean', 'banned']
        legend_elements = [mpatches.Patch(color=self.NODE_COLORS[t], label=t.replace('_', ' ').title()) 
                          for t in legend_items]
        ax.legend(handles=legend_elements, loc='upper left', fontsize=9)
        
        fraud_pct = (self.stats['fraud_transactions'] / max(self.stats['total_transactions'], 1) * 100)
        stats_text = (
            f"Nodes: {self.G.number_of_nodes()} | Edges: {self.G.number_of_edges()}\n"
            f"Txs: {int(self.stats['total_transactions']):,} | Vol: ${self.stats['total_volume']:,.0f}\n"
            f"Fraud: {int(self.stats['fraud_transactions']):,} ({fraud_pct:.1f}%) | ${self.stats['fraud_volume']:,.0f}"
        )
        ax.text(0.02, 0.02, stats_text, transform=ax.transAxes, fontsize=9,
                verticalalignment='bottom', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        ax.set_axis_off()
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
            print(f"💾 Saved to {save_path}")
        
        plt.show()
        return fig
    
    def visualize_html(self, output_path='transaction_graph.html'):
        """Create interactive HTML visualization."""
        if not PLOTLY_AVAILABLE:
            print("❌ Plotly not installed. Run: pip install plotly")
            return None
        
        if self.G.number_of_nodes() == 0:
            print("❌ No data!")
            return None
        
        if not self.node_types:
            self.assign_node_types()
        
        print("📐 Computing layout for HTML...")
        pos = nx.spring_layout(self.G, k=2, iterations=50, seed=42)
        
        edge_x, edge_y = [], []
        for u, v in self.G.edges():
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])
        
        edge_trace = go.Scatter(x=edge_x, y=edge_y, mode='lines',
                                line=dict(width=1, color='#888'), hoverinfo='none', opacity=0.5)
        
        node_x = [pos[n][0] for n in self.G.nodes()]
        node_y = [pos[n][1] for n in self.G.nodes()]
        node_colors = [self.NODE_COLORS.get(self.node_types.get(n, 'unknown'), '#95a5a6') 
                       for n in self.G.nodes()]
        
        node_text = []
        for n in self.G.nodes():
            vol = sum(d['weight'] for _, _, d in self.G.in_edges(n, data=True))
            vol += sum(d['weight'] for _, _, d in self.G.out_edges(n, data=True))
            status = "🚫 BANNED" if n in self.banned_nodes else ""
            node_text.append(f"<b>ID:</b> {n}<br><b>Type:</b> {self.node_types.get(n, '?')}<br>"
                            f"<b>Volume:</b> ${vol:,.0f}<br>{status}")
        
        node_trace = go.Scatter(x=node_x, y=node_y, mode='markers', hoverinfo='text', text=node_text,
                               marker=dict(color=node_colors, size=15, line=dict(width=2, color='white')))
        
        fig = go.Figure(
            data=[edge_trace, node_trace],
            layout=go.Layout(
                title='Transaction Network (Interactive)',
                showlegend=False, hovermode='closest',
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                plot_bgcolor='white',
                annotations=[dict(
                    text=f"Nodes: {self.G.number_of_nodes()} | Edges: {self.G.number_of_edges()} | "
                         f"Volume: ${self.stats['total_volume']:,.0f}",
                    showarrow=False, xref="paper", yref="paper", x=0.01, y=0.01, font=dict(size=12)
                )]
            )
        )
        
        fig.write_html(output_path)
        print(f"💾 Saved to {output_path}")
        return fig
    
    def print_summary(self):
        """Print summary."""
        print("\n" + "=" * 60)
        print("TRANSACTION GRAPH SUMMARY")
        print("=" * 60)
        print(f"Nodes: {self.G.number_of_nodes()}")
        print(f"Edges: {self.G.number_of_edges()}")
        print(f"Transactions: {int(self.stats['total_transactions']):,}")
        print(f"Total Volume: ${self.stats['total_volume']:,.0f}")
        print(f"Fraud Txs: {int(self.stats['fraud_transactions']):,}")
        print(f"Fraud Volume: ${self.stats['fraud_volume']:,.0f}")
        print(f"Banned: {len(self.banned_nodes)}")
        print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description='Visualize fraud simulation transaction graph')
    parser.add_argument('--output', choices=['screen', 'png', 'html', 'all'], default='screen')
    parser.add_argument('--layout', choices=['spring', 'kamada_kawai', 'circular'], default='spring')
    parser.add_argument('--no-labels', action='store_true')
    parser.add_argument('--no-highlight', action='store_true')
    
    args = parser.parse_args()
    
    viz = TransactionGraphVisualizer()
    
    if viz.load_from_stream():
        viz.load_identity_map()
        viz.load_banned_nodes()
        viz.load_fraud_alerts()
        viz.print_summary()
        
        if args.output in ['png', 'all']:
            viz.visualize(layout=args.layout, show_labels=not args.no_labels,
                         highlight_fraud=not args.no_highlight, save_path='transaction_graph.png')
        
        if args.output in ['html', 'all']:
            viz.visualize_html('transaction_graph.html')
        
        if args.output == 'screen':
            viz.visualize(layout=args.layout, show_labels=not args.no_labels,
                         highlight_fraud=not args.no_highlight)
    else:
        print("\n⚠️  No data found. Make sure:")
        print("   1. Redis is running")
        print("   2. Simulation has been executed")
        print("   3. Check: redis-cli XLEN money_flow")


if __name__ == "__main__":
    main()