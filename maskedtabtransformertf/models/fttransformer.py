import numpy as np
import tensorflow as tf
from tabtransformertf.models.tabtransformer import TransformerBlock
from tensorflow.keras.layers import (
    Dense,
    Flatten,
)
import math as m
from tabtransformertf.models.embeddings import CEmbedding, NEmbedding


class FTTransformerEncoder(tf.keras.Model):
    def __init__(
        self,
        categorical_features: list,
        numerical_features: list,
        numerical_data: np.array,
        categorical_data: np.array,
        y: np.array = None,
        task: str = None,
        embedding_dim: int = 32,
        depth: int = 4,
        heads: int = 8,
        attn_dropout: float = 0.1,
        ff_dropout: float = 0.1,
        numerical_embedding_type: str = 'linear',
        numerical_bins: int = None,
        ple_tree_params: dict = {},
        explainable=False,
    ):
        """FTTransformer Encoder
        Args:
            categorical_features (list): names of categorical features
            numerical_features (list): names of numeric features
            categorical_lookup (dict): dictionary with categorical feature names as keys and adapted StringLookup layers as values
            out_dim (int): model output dimensions
            out_activation (str): model output activation
            embedding_dim (int, optional): embedding dimensions. Defaults to 32.
            depth (int, optional): number of transformer blocks. Defaults to 4.
            heads (int, optional): number of attention heads. Defaults to 8.
            attn_dropout (float, optional): dropout rate in transformer. Defaults to 0.1.
            ff_dropout (float, optional): dropout rate in mlps. Defaults to 0.1.
            mlp_hidden_factors (list[int], optional): numbers by which we divide dimensionality. Defaults to [2, 4].
            numerical_embeddings (dict, optional): dictionary with numerical feature names as keys and adapted numerical embedding layers as values. Defaults to None.
            numerical_embedding_type (str, optional): name of the numerical embedding procedure. Defaults to linear.
            use_column_embedding (bool, optional): flag to use fixed column positional embeddings. Defaults to True.
            explainable (bool, optional): flag to output importances inferred from attention weights. Defaults to False.
        """

        super(FTTransformerEncoder, self).__init__()
        self.numerical = numerical_features
        self.categorical = categorical_features
        self.numerical_embedding_type = numerical_embedding_type
        self.embedding_dim = embedding_dim
        self.explainable = explainable
        self.depth = depth
        self.heads = heads

        # Two main embedding modules
        if len(self.numerical) > 0:
            self.numerical_embeddings = NEmbedding(
                feature_names=self.numerical,
                X=numerical_data,
                y=y,
                task=task,
                emb_dim=embedding_dim,
                emb_type=numerical_embedding_type,
                n_bins=numerical_bins,
                tree_params=ple_tree_params
            )
        if len(self.categorical) > 0:
            self.categorical_embeddings = CEmbedding(
                feature_names=self.categorical,
                X=categorical_data,
                emb_dim=embedding_dim
            )

        # Transformers
        self.transformers = []
        for _ in range(depth):
            self.transformers.append(
                TransformerBlock(
                    embedding_dim,
                    heads,
                    embedding_dim,
                    att_dropout=attn_dropout,
                    ff_dropout=ff_dropout,
                    explainable=self.explainable,
                    post_norm=False,  # FT-Transformer uses pre-norm
                )
            )
        self.flatten_transformer_output = Flatten()


    def call(self, inputs):
        
        transformer_inputs = []

        # If categorical features, add to list
        if len(self.categorical) > 0:
            cat_input = []
            for c in self.categorical:
                cat_input.append(inputs[c])

            cat_input = tf.stack(cat_input, axis=1)[:, :, 0]
            cat_embs = self.categorical_embeddings(cat_input)
            transformer_inputs += [cat_embs]

        # If numerical features, add to list
        if len(self.numerical) > 0:
            num_input = []
            for n in self.numerical:
                num_input.append(inputs[n])
            num_input = tf.stack(num_input, axis=1)[:, :, 0]
            num_embs = self.numerical_embeddings(num_input)
            transformer_inputs += [num_embs]

        # Prepare for Transformer
        transformer_inputs = tf.concat(transformer_inputs, axis=1)
        importances = []

        # Pass through Transformer blocks
        for transformer in self.transformers:
            if self.explainable:
                transformer_inputs, att_weights = transformer(
                    transformer_inputs)
                importances.append(tf.reduce_sum(
                    att_weights[:, :, 0, :], axis=1))
            else:
                transformer_inputs = transformer(transformer_inputs)

        if self.explainable:
            # Sum across the layers
            importances = tf.reduce_sum(tf.stack(importances), axis=0) / (
                self.depth * self.heads
            )
            return transformer_inputs, importances
        else:
            return transformer_inputs


class FTTransformer(tf.keras.Model):
    def __init__(
        self,
        out_dim: int,
        out_activation: str,
        categorical_features: list = None,
        numerical_features: list = None,
        categorical_lookup: dict = None,
        embedding_dim: int = 32,
        depth: int = 4,
        heads: int = 8,
        attn_dropout: float = 0.1,
        ff_dropout: float = 0.1,
        numerical_embedding_type: str = None,
        numerical_embeddings: dict = None,
        explainable=False,
        encoder=None,
    ):
        super(FTTransformer, self).__init__()

        # Initialise encoder
        if encoder:
            self.encoder = encoder
        else:
            self.encoder = FTTransformerEncoder(
                categorical_features=categorical_features,
                numerical_features=numerical_features,
                embedding_dim=embedding_dim,
                depth=depth,
                heads=heads,
                attn_dropout=attn_dropout,
                ff_dropout=ff_dropout,
                numerical_embedding_type=numerical_embedding_type,
                explainable=explainable,
            )

        #Reconstruction layers
        self.num_features = (len(self.encoder.numerical) if self.encoder.numerical is not None else 0) + \
               (len(self.encoder.categorical) if self.encoder.categorical is not None else 0)

        self.masked_predictions_layer = Dense(units=self.num_features)


    def call(self, inputs):
        if self.encoder.explainable:
            x, expl = self.encoder(inputs)
        else:
            x = self.encoder(inputs)

        print(x.shape)
        reshaped_x = tf.reshape(x, [-1, self.num_features*self.embedding_dim])
        print(reshaped_x.shape)
        masked_preds = self.masked_predictions_layer(reshaped_x)
        output_dict = {"masked_preds": masked_preds}

        if self.encoder.explainable:
            # Explainable models return three outputs
            output_dict["importances"] = expl

        return output_dict

    def masked_mse(self, y_true, y_pred):
        return tf.reduce_mean(tf.square(y_true - y_pred))

    def train_step(self, data):
        
        x = data
        y=x #unmasked input is the output

        with tf.GradientTape() as tape:
            y_pred = self(x, training=True)  # Forward pass

            # Compute the loss value.
            # The loss function is configured in `compile()`
            y_true_tensor = tf.cast(tf.concat(list(y.values()), axis=-1),dtype='float32')
            loss = self.masked_mse(y_true_tensor, y_pred["masked_preds"])

        # Compute gradients
        trainable_vars = self.trainable_variables
        gradients = tape.gradient(loss, trainable_vars)

        # Update weights
        self.optimizer.apply_gradients(zip(gradients, trainable_vars))

        # Update the metrics.
        for metric in self.metrics:
            if metric.name == "loss":
                metric.update_state(loss)
            else:
                metric.update_state(y, y_pred["masked_preds"])
        # Return a dict mapping metric names to current value
        return {m.name: m.result() for m in self.metrics}
