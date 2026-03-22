import torch
import torch.nn as nn


class LSTMAutoencoder(nn.Module):
    """
    Generic LSTM autoencoder.

    - input_dim controls the feature dimension fed into the encoder.
    - output_dim defaults to input_dim but can be smaller. This is useful for
      gap-filling, where we input [masked_value, observed_mask] and reconstruct
      only the value channel.
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 32,
        num_layers: int = 1,
        dropout: float = 0.1,
        output_dim: int | None = None,
    ):
        super().__init__()
        self.input_dim = int(input_dim)
        self.output_dim = int(output_dim if output_dim is not None else input_dim)
        self.encoder = nn.LSTM(
            input_size=self.input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.decoder = nn.LSTM(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.to_hidden = nn.Linear(hidden_dim, hidden_dim)
        self.out = nn.Linear(hidden_dim, self.output_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (h, c) = self.encoder(x)           # (L,B,H)
        h_last = h[-1]                        # (B,H)
        batch_size, seq_len, _ = x.shape
        dec_in_step = torch.tanh(self.to_hidden(h_last)).unsqueeze(1)  # (B,1,H)
        dec_in = dec_in_step.repeat(1, seq_len, 1)  # (B,T,H)
        y, _ = self.decoder(dec_in, (h, c))   # (B,T,H)
        return self.out(y)                    # (B,T,output_dim)
