import numpy as np
import torch
import torch.nn as nn


class ConvBlockTransposed(nn.Module):
    def __init__(self, ticker_dim, data_point_dim, shift_dim, transform_dim, output_dim, args):
        '''
        :param ticker_dim     : number of tickers used for the data
        :param data_point_dim : dim of a given data point (e.g. ohlc+volume = 5)
        :param shift_dim      : dim of shifts in time scales (e.g. 4 different shifts backs for returns)
        :param transform_dim  : dim of different transforms (e.g. 4 different sckit-transforms)
        :param output_dim     : dim of outputs, should be a multiple of ticker_dim (e.g. ticker_dim * 2)
        '''
        assert output_dim % ticker_dim == 0, 'output_dim should be divisible by ticker_dim'

        self.input_dim = ticker_dim * shift_dim * data_point_dim * transform_dim
        self.transform_dim = transform_dim
        self.output_dim = output_dim
        self.label_dim = output_dim // ticker_dim
        self.conv_channel = self.label_dim * args.const_factor

        super(ConvBlockTransposed, self).__init__()

        self.c1 = nn.Conv1d(self.conv_channel,
                            self.conv_channel,
                            kernel_size=(shift_dim * data_point_dim,),
                            stride=(shift_dim * data_point_dim),
                            bias=False)
        dim_after_c1 = self._compute_dim_after_conv1()[-1]
        self.l1 = nn.LayerNorm(dim_after_c1)
        self.ct1 = nn.ConvTranspose1d(self.conv_channel,
                                      self.conv_channel,
                                      kernel_size=(shift_dim * data_point_dim,),
                                      stride=(shift_dim * data_point_dim))

        self.c2 = nn.Conv1d(self.conv_channel,
                            self.conv_channel,
                            kernel_size=(transform_dim,),
                            stride=transform_dim,
                            bias=False)
        dim_after_c2 = self._compute_dim_after_conv2()[-1]
        self.l2 = nn.LayerNorm(dim_after_c2)
        self.ct2 = nn.ConvTranspose1d(self.conv_channel,
                                      self.conv_channel,
                                      kernel_size=(transform_dim,),
                                      stride=transform_dim)

        self.args = args
        if self.args.linear_dim > 0:
            self.linear_1 = nn.Linear(dim_after_c2,
                                      args.linear_dim,
                                      bias=False)
            self.linear_2 = nn.Linear(args.linear_dim,
                                      dim_after_c2,
                                      bias=False)

    def _compute_dim_after_conv1(self):
        c1_output = self._conv1_test_input()
        return c1_output.shape

    def _compute_dim_after_conv2(self):
        c2_output = self._conv2_test_input()
        return c2_output.shape

    def _conv1_test_input(self):
        temp_input = torch.ones((1, self.conv_channel, self.input_dim), requires_grad=False)
        return self.c1(temp_input)

    def _conv2_test_input(self):
        conv_1_out = self._conv1_test_input()
        return self.c2(conv_1_out)

    def forward(self, input):
        out = torch.relu(self.l1(self.c1(input)))

        out = torch.relu(self.l2(self.c2(out)))

        if self.args.linear_dim > 0:
            out = torch.tanh(self.linear_1(out))
            out = torch.tanh(self.linear_2(out))

        out = self.ct2(out)
        out = self.ct1(out) + input
        return out


class ConvBlockTransposedNew(nn.Module):
    def __init__(self, ticker_dim, input_dim, data_point_dim, shift_dim, transform_dim, output_dim, args):
        '''
        :param ticker_dim     : number of tickers used for the data
        :param data_point_dim : dim of a given data point (e.g. ohlc+volume = 5)
        :param shift_dim      : dim of shifts in time scales (e.g. 4 different shifts backs for returns)
        :param transform_dim  : dim of different transforms (e.g. 4 different sckit-transforms)
        :param output_dim     : dim of outputs, should be a multiple of ticker_dim (e.g. ticker_dim * 2)
        '''
        assert output_dim % ticker_dim == 0, 'output_dim should be divisible by ticker_dim'

        self.ticker_dim = ticker_dim
        self.input_dim = input_dim
        self.transform_dim = transform_dim
        self.output_dim = output_dim
        self.label_dim = output_dim // ticker_dim
        self.conv_channel = self.label_dim * args.const_factor

        self.c1_kernel_size = input_dim // transform_dim

        super(ConvBlockTransposedNew, self).__init__()

        self.c1 = nn.Conv1d(self.conv_channel,
                            self.conv_channel,
                            kernel_size=self.c1_kernel_size,
                            stride=self.c1_kernel_size,
                            bias=False)
        dim_after_c1 = self._compute_dim_after_conv1()[1:]
        self.l1 = nn.LayerNorm(dim_after_c1)
        self.ct1 = nn.ConvTranspose1d(self.conv_channel,
                                      self.conv_channel,
                                      kernel_size=self.c1_kernel_size,
                                      stride=self.c1_kernel_size)

        self.c2 = nn.Conv1d(self.conv_channel,
                            self.conv_channel,
                            kernel_size=(transform_dim,),
                            stride=transform_dim,
                            bias=False)
        dim_after_c2 = self._compute_dim_after_conv2()[1:]
        self.l2 = nn.LayerNorm(dim_after_c2)
        self.ct2 = nn.ConvTranspose1d(self.conv_channel,
                                      self.conv_channel,
                                      kernel_size=(transform_dim,),
                                      stride=transform_dim)

        self.args = args
        if self.args.linear_dim > 0:

            if len(dim_after_c2) > 1:
                dim_after_c2 = dim_after_c2[-1]

            self.linear_1 = nn.Linear(dim_after_c2,
                                      args.linear_dim,
                                      bias=False)
            self.linear_2 = nn.Linear(args.linear_dim,
                                      dim_after_c2,
                                      bias=False)

    def _compute_dim_after_conv1(self):
        c1_output = self._conv1_test_input()
        return c1_output.shape

    def _compute_dim_after_conv2(self):
        c2_output = self._conv2_test_input()
        return c2_output.shape

    def _conv1_test_input(self):
        temp_input = torch.ones((1, self.conv_channel, self.input_dim*self.ticker_dim), requires_grad=False)
        return self.c1(temp_input)

    def _conv2_test_input(self):
        conv_1_out = self._conv1_test_input()
        return self.c2(conv_1_out)

    def forward(self, input):
        out = torch.relu(self.l1(self.c1(input)))

        out = torch.relu(self.l2(self.c2(out)))

        if self.args.linear_dim > 0:
            out = torch.tanh(self.linear_1(out))
            out = torch.tanh(self.linear_2(out))

        out = self.ct2(out)
        out = self.ct1(out) + input
        return out


class ConvBlockWrapper(nn.Module):
    def __init__(self, ticker_dim, data_point_dim, shift_dim, transform_dim, output_dim, args):
        '''
        :param ticker_dim     : number of tickers used for the data
        :param data_point_dim : dim of a given data point (e.g. ohlc+volume = 5)
        :param shift_dim      : dim of shifts in time scales (e.g. 4 different shifts backs for returns)
        :param transform_dim  : dim of different transforms (e.g. 4 different sckit-transforms)
        :param output_dim     : dim of outputs, should be a multiple of ticker_dim (e.g. ticker_dim * 2)
        '''
        assert output_dim % ticker_dim == 0, 'output_dim should be divisible by ticker_dim'

        self.input_dim = ticker_dim * shift_dim * data_point_dim * transform_dim
        # self.transform_dim = transform_dim
        self.output_dim = output_dim
        self.label_dim = output_dim // ticker_dim
        self.conv_channel = self.label_dim * args.const_factor

        super(ConvBlockWrapper, self).__init__()
        self.original_c1 = nn.Conv1d(1,
                                     self.conv_channel,
                                     kernel_size=(shift_dim * data_point_dim,),
                                     stride=(shift_dim * data_point_dim),
                                     bias=False)
        original_dim_after_c1 = self._compute_dim_after_original_conv1()
        self.original_l1 = nn.LayerNorm(original_dim_after_c1[1:])
        self.original_ct1 = nn.ConvTranspose1d(self.conv_channel,
                                               self.conv_channel,
                                               kernel_size=(shift_dim * data_point_dim,),
                                               stride=(shift_dim * data_point_dim))

        c2_blocks = [ConvBlockTransposed(ticker_dim,
                                         data_point_dim,
                                         shift_dim,
                                         transform_dim,
                                         output_dim,
                                         args) for _ in range(args.block_depth)]
        self.mid_blocks = nn.Sequential(*c2_blocks)

        self.c1 = nn.Conv1d(self.conv_channel,
                            self.conv_channel,
                            kernel_size=(shift_dim * data_point_dim,),
                            stride=(shift_dim * data_point_dim),
                            bias=False)
        self.c2 = nn.Conv1d(self.conv_channel,
                            self.label_dim,
                            kernel_size=(transform_dim,),
                            stride=transform_dim,
                            bias=False)

    def _compute_dim_after_original_conv1(self):
        c1_output = self._conv1_test_input()
        return c1_output.shape

    def _conv1_test_input(self):
        temp_input = torch.ones((1, 1, self.input_dim), requires_grad=False)
        return self.original_c1(temp_input)

    def forward(self, input):
        input = input.unsqueeze(1)
        out = self.original_ct1(torch.relu(self.original_l1(self.original_c1(input))))
        out = self.mid_blocks(out)
        out = self.c1(out)
        out = self.c2(out)
        return torch.sigmoid(out.reshape((-1, self.output_dim)).contiguous())

    def show_parameter_shapes(self):
        '''
        Use this function as a reminder of horrible param sizes...
        '''
        return [param.shape for child in self.children() for param in child.parameters()]


class ConvBlockWrapperNew(nn.Module):
    def __init__(self, ticker_dim, input_dim, data_point_dim, shift_dim, transform_dim, output_dim, args):
        '''
        :param ticker_dim     : number of tickers used for the data
        :param input_dim      : dim of input
        :param data_point_dim (Deprecate) : dim of a given data point (e.g. ohlc+volume = 5)
        :param shift_dim      (Deprecate) : dim of shifts in time scales (e.g. 4 different shifts backs for returns)
        :param transform_dim  : dim of different transforms (e.g. 4 different sckit-transforms)
        :param output_dim     : dim of outputs, should be a multiple of ticker_dim (e.g. ticker_dim * 2)
        '''
        assert output_dim % ticker_dim == 0, '{} % {} != 0'.format(output_dim, ticker_dim)
        assert input_dim % transform_dim == 0, '{} % {} != 0'.format(input_dim, ticker_dim)

        self.ticker_dim = ticker_dim
        self.input_dim = input_dim
        self.transform_dim = transform_dim
        self.output_dim = output_dim
        self.label_dim = output_dim // ticker_dim
        self.conv_channel = self.label_dim * args.const_factor

        self.c1_kernel_size = input_dim // transform_dim

        super(ConvBlockWrapperNew, self).__init__()
        self.original_c1 = nn.Conv1d(1,
                                     self.conv_channel,
                                     kernel_size=self.c1_kernel_size,
                                     stride=self.c1_kernel_size,
                                     bias=False)
        original_dim_after_c1 = self._compute_dim_after_original_conv1()
        self.original_l1 = nn.LayerNorm(original_dim_after_c1[1:])
        self.original_ct1 = nn.ConvTranspose1d(self.conv_channel,
                                               self.conv_channel,
                                               kernel_size=self.c1_kernel_size,
                                               stride=self.c1_kernel_size)

        c2_blocks = [ConvBlockTransposedNew(ticker_dim,
                                            input_dim,
                                            data_point_dim,
                                            shift_dim,
                                            transform_dim,
                                            output_dim,
                                            args) for _ in range(args.block_depth)]
        self.mid_blocks = nn.Sequential(*c2_blocks)

        self.c1 = nn.Conv1d(self.conv_channel,
                            self.conv_channel,
                            kernel_size=self.c1_kernel_size,
                            stride=self.c1_kernel_size,
                            bias=False)
        self.c2 = nn.Conv1d(self.conv_channel,
                            self.label_dim,
                            kernel_size=transform_dim,
                            stride=transform_dim,
                            bias=False)

    def _compute_dim_after_original_conv1(self):
        c1_output = self._conv1_test_input()
        return c1_output.shape

    def _conv1_test_input(self):
        temp_input = torch.ones((1, 1, self.input_dim*self.ticker_dim), requires_grad=False)
        return self.original_c1(temp_input)

    def forward(self, input):
        input = input.unsqueeze(1)
        out = self.original_ct1(torch.relu(self.original_l1(self.original_c1(input))))
        out = self.mid_blocks(out)
        out = self.c1(out)
        out = self.c2(out)
        return torch.sigmoid(out.reshape((-1, self.output_dim)).contiguous())

    def show_parameter_shapes(self):
        '''
        Use this function as a reminder of horrible param sizes...
        '''
        return [param.shape for child in self.children() for param in child.parameters()]


class Classifier(nn.Module):
    def __init__(self, ticker_dim, data_point_dim, shift_dim, transform_dim, output_dim):
        '''
        :param ticker_dim     : dim of tickers used for the data
        :param data_point_dim : dim of a given data point (e.g. ohlc+volume = 5)
        :param shift_dim      : dim of shifts in time scales (e.g. 4 different shifts backs for returns)
        :param transform_dim  : dim of different transforms (e.g. 4 different sckit-transforms)
        :param output_dim     : dim of outputs, should be a multiple of ticker_dim (e.g. ticker_dim * 2)
        '''
        assert output_dim % ticker_dim == 0, 'output_dim should be divisible by ticker_dim'

        self.input_dim = ticker_dim * shift_dim * data_point_dim * transform_dim
        self.output_dim = output_dim

        self.conv_channel = output_dim // ticker_dim

        super(Classifier, self).__init__()

        self.l1 = nn.Linear(self.input_dim, output_dim)

        self.c1 = nn.Conv1d(1,
                            self.conv_channel,
                            kernel_size=shift_dim * data_point_dim,
                            stride=shift_dim * data_point_dim,
                            bias=False)
        self.c2 = nn.Conv1d(self.conv_channel,
                            self.conv_channel,
                            kernel_size=transform_dim,
                            stride=transform_dim,
                            bias=False)

        self.linear_repeat_dim, self.conv_repeat_dim = self._return_repeat_dim()

        self.c3 = nn.Conv1d(self.conv_channel, 1, (1,))

    def _compute_conv_output_shape(self):
        temp_input = torch.ones((1, 1, self.input_dim), requires_grad=False)
        return self.c2(self.c1(temp_input)).shape

    def _compute_repeat_dim(self):
        temp_input = torch.ones((1, self.input_dim), requires_grad=False)
        linear_output_shape = self.l1(temp_input).unsqueeze(1).shape

        conv_output_shape = self._compute_conv_output_shape()

        return [conv / linear for conv, linear in
                zip(conv_output_shape, linear_output_shape)]

    def _return_repeat_dim(self):
        conv_div_linear_dims = self._compute_repeat_dim()

        linear_output_repeat_dim = [item if item >= 1.0 else 1.0 for item in conv_div_linear_dims]
        conv_output_repeat_dim = [1.0 if item >= 1.0 else 1 / item for item in conv_div_linear_dims]

        linear_output_repeat_dim, conv_output_repeat_dim = list(map(lambda x: np.array(x).astype(int),
                                                                    [linear_output_repeat_dim, conv_output_repeat_dim]))

        return linear_output_repeat_dim, conv_output_repeat_dim

    def forward(self, input):
        linear = self.l1(input)
        linear = torch.relu(linear).unsqueeze(1)
        linear = linear.repeat(*self.linear_repeat_dim)

        conv = input.unsqueeze(1)
        conv = torch.relu(self.c1(conv))
        conv = torch.relu(self.c2(conv))
        conv = conv.repeat(*self.conv_repeat_dim)

        out = linear + conv
        return torch.sigmoid(self.c3(out)).squeeze(1)

    def show_parameter_shapes(self):
        '''
        Use this function as a reminder of horrible param sizes...
        '''
        return [param.shape for child in self.children() for param in child.parameters()]


class Flatten(nn.Module):
    def forward(self, input):
        return input.view(input.size(0), -1)


class ContinuousModelBasicConvolution(torch.nn.Module):
    def __init__(self,
                 input_shape,
                 conv_hidden_size,
                 conv_kernel_size,
                 linear_output_size,
                 final_output_size):
        '''
        :param input_shape: tuple of (num_tickers, num_running_days)
        :param conv_hidden_size: hidden dimension
        :param conv_kernel_size: kernel dimension for 1d convolution
        :param linear_output_size: linear output dimension
        :param final_output_size: num_tickers
        '''
        assert isinstance(input_shape, tuple)
        super(ContinuousModelBasicConvolution, self).__init__()
        self.c1 = nn.Conv1d(input_shape[0], conv_hidden_size, conv_kernel_size, stride=2)
        self.b1 = nn.BatchNorm1d(conv_hidden_size)
        self.c2 = nn.Conv1d(conv_hidden_size, conv_hidden_size, conv_kernel_size, stride=1)
        self.b2 = nn.BatchNorm1d(conv_hidden_size)
        # self.c3 = nn.Conv1d(conv_hidden_size, conv_hidden_size, conv_kernel_size//2, stride=1)
        # self.b3 = nn.BatchNorm1d(conv_hidden_size)

        self.flatten = Flatten()

        flatten_dim = self._get_conv_output(input_shape)

        self.linear1 = nn.Linear(flatten_dim, linear_output_size)
        self.linear2 = nn.Linear(linear_output_size, final_output_size)

    def _forward_features(self, x):
        x = torch.relu(self.b1(self.c1(x)))
        # x = torch.relu(self.c1(x))
        x = torch.relu(self.b2(self.c2(x)))
        # x = torch.relu(self.c2(x))
        # x = torch.relu(self.b3(self.c3(x)))
        # x = torch.relu(self.c3(x))
        return x

    def _get_conv_output(self, shape):
        batch_size = 1
        _input = torch.rand(batch_size, *shape)
        _output = self._forward_features(_input).detach()
        n_size = _output.data.view(batch_size, -1).size(1)
        return n_size

    def forward(self, x):
        # x is being permuted...
        x = self._forward_features(x.permute(0, 2, 1))
        x = self.flatten(x)
        x = torch.relu(self.linear1(x))
        return torch.tanh(self.linear2(x))


class Encoder(nn.Module):
    def __init__(self, input_shape, final_output_size):
        super(Encoder, self).__init__()
        self.c1 = nn.Conv1d(input_shape[0], final_output_size * 2, (4,), 4)
        self.c2 = nn.Conv1d(final_output_size * 2, final_output_size * 1, (1,), 1)
        self.c3 = nn.Conv1d(final_output_size * 1, 1, (1,), 1)

    def forward(self, x):
        x = self.c1(x)
        x = torch.relu(x)
        x = self.c2(x)
        x = torch.relu(x)
        x = self.c3(x)
        return torch.tanh(x)


class Decoder(nn.Module):
    def __init__(self, input_shape, final_output_size):
        super(Decoder, self).__init__()
        self.c1 = nn.ConvTranspose1d(1,
                                     final_output_size * 1, (1,), stride=1)
        self.c2 = nn.ConvTranspose1d(final_output_size * 1,
                                     final_output_size * 2, (1,), 1)
        self.c3 = nn.ConvTranspose1d(final_output_size * 2,
                                     input_shape[0], (4,), 4)

    def forward(self, x):
        x = self.c1(x)
        x = torch.relu(x)
        x = self.c2(x)
        x = torch.relu(x)
        x = self.c3(x)
        return x


class AutoEncoder(nn.Module):
    def __init__(self, input_shape, final_output_size):
        super(AutoEncoder, self).__init__()
        self.encoder = Encoder(input_shape, final_output_size)
        self.decoder = Decoder(input_shape, final_output_size)

    def forward(self, x):
        x = self.encoder(x)
        return self.decoder(x)